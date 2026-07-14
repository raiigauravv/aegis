"""LinUCB routing policy: serve + learn + snapshot.

Actions (direct invoke or SQS feedback records):
  {"action": "select", "ticket_id": ...}  -> choose an arm for an enriched ticket,
      record BANDIT items and a trace event. Tier-3 tickets are REFUSED here:
      governance > optimization, they never enter the bandit.
  SQS records from the feedback queue: {"ticket_id", "reward"} -> update stats.
  {"action": "snapshot"} -> dump policy state to S3 (EventBridge nightly), so
      policy evolution is replayable.

Sufficient statistics live in DynamoDB: PK=BANDIT SK=ARM#<i>.
"""

import json
import os
import time
from datetime import UTC, datetime
from typing import Any

import boto3
import numpy as np
from aegis_core import store
from aegis_core.models import TraceEvent
from aegis_core.tracing import get_logger
from bandit_lib.context import build_context
from bandit_lib.linucb import ARMS, LinUCB

logger = get_logger("bandit_policy")
ALPHA = float(os.environ.get("BANDIT_ALPHA", "1.0"))
_s3 = None


def _load_model() -> LinUCB:
    resp = store.table().query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": "BANDIT"},
    )
    items = sorted(resp.get("Items", []), key=lambda i: str(i["SK"]))
    if len(items) != len(ARMS):
        return LinUCB(alpha=ALPHA)
    state = [json.loads(str(i["state"])) for i in items]
    return LinUCB.from_state(state, alpha=ALPHA)


def _save_model(model: LinUCB) -> None:
    for i, arm_state in enumerate(model.to_state()):
        store.table().put_item(Item={"PK": "BANDIT", "SK": f"ARM#{i}", "state": json.dumps(arm_state)})


def select(ticket_id: str) -> dict[str, Any]:
    start = time.perf_counter()
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(f"ticket {ticket_id} not found")
    meta = ticket["meta"]
    if int(meta.get("risk_tier", 1) or 1) >= 3:
        # Governance over optimization: tier 3 is always a human.
        return {"ticket_id": ticket_id, "arm": "escalate_human", "bandit": False}

    model = _load_model()
    x = build_context(meta)
    arm_idx = model.select(x)
    latency = round((time.perf_counter() - start) * 1000, 2)
    store.update_meta(ticket_id, {"routing_arm": ARMS[arm_idx], "routing_context": json.dumps(x.tolist())})
    store.append_trace(
        TraceEvent(
            ticket_id=ticket_id,
            service="bandit_policy",
            step="route",
            latency_ms=latency,
            detail={"arm": ARMS[arm_idx], "alpha": str(ALPHA), "pulls": str(model.pulls[arm_idx])},
        )
    )
    logger.info(
        "arm selected",
        extra={"ticket_id": ticket_id, "step": "route", "latency_ms": latency},
    )
    return {"ticket_id": ticket_id, "arm": ARMS[arm_idx], "bandit": True}


def update(ticket_id: str, reward: float) -> None:
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(f"ticket {ticket_id} not found")
    meta = ticket["meta"]
    arm_name = meta.get("routing_arm")
    ctx_json = meta.get("routing_context")
    if not arm_name or not ctx_json:
        logger.info(
            "no routing decision to update",
            extra={"ticket_id": ticket_id, "step": "learn"},
        )
        return
    model = _load_model()
    x = np.array(json.loads(str(ctx_json)))
    model.update(ARMS.index(str(arm_name)), x, reward)
    _save_model(model)
    store.append_trace(
        TraceEvent(
            ticket_id=ticket_id,
            service="bandit_policy",
            step="learn",
            detail={"arm": str(arm_name), "reward": str(reward)},
        )
    )


def snapshot() -> dict[str, str]:
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    model = _load_model()
    key = f"bandit/snapshots/{datetime.now(UTC).strftime('%Y-%m-%dT%H%M')}.json"
    _s3.put_object(
        Bucket=os.environ["SNAPSHOT_BUCKET"],
        Key=key,
        Body=json.dumps({"alpha": ALPHA, "arms": model.to_state()}),
    )
    logger.info("policy snapshot", extra={"step": "snapshot", "detail": {"key": key}})
    return {"snapshot": key}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if "Records" in event:  # feedback queue
        failures = []
        for record in event["Records"]:
            try:
                body = json.loads(record["body"])
                update(body["ticket_id"], float(body["reward"]))
            except Exception:
                logger.error("update failed", extra={"step": "learn"}, exc_info=True)
                failures.append({"itemIdentifier": record["messageId"]})
        return {"batchItemFailures": failures}
    action = event.get("action")
    if action == "select":
        return select(event["ticket_id"])
    if action == "snapshot":
        return snapshot()
    raise ValueError(f"unknown action {action!r}")
