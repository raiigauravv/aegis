"""Public HTTP surface (API Gateway payload v2):

    POST /tickets        -> validate, enqueue TicketSubmission, 202 {ticket_id}
    GET  /tickets/{id}   -> META + trace timeline
    GET  /               -> the demo frontend (single static page, bundled in the zip)

The API only enqueues; persistence belongs to intake_router. That keeps the write
path async and lets SQS absorb bursts beyond this account's Lambda concurrency cap.
"""

import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3
from aegis_core import store
from aegis_core.models import TicketSubmission, new_ticket_id
from aegis_core.tracing import get_logger
from pydantic import ValidationError

logger = get_logger("ticket_api")

_sqs = None


def sqs() -> Any:
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs")
    return _sqs


def _response(status: int, body: Any, content_type: str = "application/json") -> dict[str, Any]:
    payload = body if isinstance(body, str) else json.dumps(body)
    return {
        "statusCode": status,
        "headers": {"content-type": content_type},
        "body": payload,
    }


@lru_cache(maxsize=1)
def _frontend() -> str:
    return (Path(__file__).parent / "index.html").read_text()


def _post_ticket(event: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        raw = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "body must be JSON"})
    try:
        sub = TicketSubmission(ticket_id=new_ticket_id(), **raw)
    except (ValidationError, TypeError) as e:
        detail = e.errors() if isinstance(e, ValidationError) else str(e)
        return _response(
            422,
            {
                "error": "invalid ticket",
                "detail": json.loads(json.dumps(detail, default=str)),
            },
        )
    sqs().send_message(QueueUrl=os.environ["QUEUE_URL"], MessageBody=sub.model_dump_json())
    logger.info(
        "ticket enqueued",
        extra={
            "ticket_id": sub.ticket_id,
            "step": "enqueue",
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        },
    )
    return _response(202, {"ticket_id": sub.ticket_id, "status": "queued"})


def _get_ticket(ticket_id: str) -> dict[str, Any]:
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        return _response(404, {"error": "not found", "ticket_id": ticket_id})
    return _response(200, ticket)


# Human feedback actions -> bandit reward (ADR-004)
_REWARDS = {
    "approve": 1.0,
    "approve_edited": 0.5,
    "heavy_edit": 0.0,
    "reject": -0.5,
    "escalated_after_send": -1.0,
}
_FEEDBACK_STATUS = {
    "approve": "approved",
    "approve_edited": "approved",
    "heavy_edit": "approved",
    "reject": "rejected",
    "escalated_after_send": "rejected",
}
_lambda = None


def _post_feedback(ticket_id: str, event: dict[str, Any]) -> dict[str, Any]:
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "body must be JSON"})
    action = body.get("action")
    if action not in _REWARDS:
        return _response(422, {"error": f"action must be one of {sorted(_REWARDS)}"})
    if store.get_ticket(ticket_id) is None:
        return _response(404, {"error": "not found", "ticket_id": ticket_id})
    reward = _REWARDS[action]
    store.append_feedback(ticket_id, {"action": action, "reward": str(reward), "by": "approval_queue"})
    store.update_meta(ticket_id, {"status": _FEEDBACK_STATUS[action]})
    sqs().send_message(
        QueueUrl=os.environ["FEEDBACK_QUEUE_URL"],
        MessageBody=json.dumps({"ticket_id": ticket_id, "reward": reward}),
    )
    logger.info("feedback recorded", extra={"ticket_id": ticket_id, "step": "feedback"})
    return _response(200, {"ticket_id": ticket_id, "action": action, "reward": reward})


def _post_route(ticket_id: str) -> dict[str, Any]:
    """Ask the bandit for a routing decision (the Phase-6 state machine's call,
    exposed over HTTP for the demo frontend and the episode simulator)."""
    global _lambda
    if _lambda is None:
        _lambda = boto3.client("lambda")
    resp = _lambda.invoke(
        FunctionName=os.environ["BANDIT_FUNCTION"],
        Payload=json.dumps({"action": "select", "ticket_id": ticket_id}).encode(),
    )
    payload = json.loads(resp["Payload"].read())
    if "errorMessage" in payload:
        code = 404 if "not found" in payload["errorMessage"] else 500
        return _response(code, {"error": payload["errorMessage"]})
    return _response(200, payload)


def _get_approvals() -> dict[str, Any]:
    """Approval queue: tickets awaiting a human. Scan is fine at demo scale;
    the at-scale answer is a sparse GSI on status (documented in architecture.md)."""
    # NB: Scan's Limit caps items EVALUATED (pre-filter), so paginate fully.
    kwargs: dict[str, Any] = {
        "FilterExpression": "SK = :m AND #s = :st",
        "ExpressionAttributeNames": {"#s": "status"},
        "ExpressionAttributeValues": {":m": "META", ":st": "awaiting_approval"},
    }
    found: list[dict[str, Any]] = []
    while True:
        resp = store.table().scan(**kwargs)
        found.extend(store._plain(i) for i in resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    items = sorted(found, key=lambda i: str(i.get("created_at", "")), reverse=True)[:25]
    for i in items:
        i.pop("PK", None)
        i.pop("SK", None)
    return _response(200, {"tickets": items})


def _get_audit(ticket_id: str) -> dict[str, Any]:
    """The complete decision chain: meta, every pipeline step with latency and
    detail, and every human action. One endpoint = the auditability demo."""
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        return _response(404, {"error": "not found", "ticket_id": ticket_id})
    return _response(
        200,
        {
            "ticket_id": ticket_id,
            "current_status": ticket["meta"].get("status"),
            "risk_tier": ticket["meta"].get("risk_tier"),
            "routing_arm": ticket["meta"].get("routing_arm"),
            "pipeline_steps": ticket["trace"],
            "human_actions": ticket["feedback"],
            "pii_note": "raw text redacted before persistence; re-identification map "
            "is in a separate table no service can read",
        },
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    route = event.get("routeKey", "")
    path_id = (event.get("pathParameters") or {}).get("id", "")
    if route == "POST /tickets":
        return _post_ticket(event)
    if route == "GET /tickets/{id}":
        return _get_ticket(path_id)
    if route == "POST /tickets/{id}/feedback":
        return _post_feedback(path_id, event)
    if route == "POST /tickets/{id}/route":
        return _post_route(path_id)
    if route == "GET /tickets/{id}/audit":
        return _get_audit(path_id)
    if route == "GET /approvals":
        return _get_approvals()
    if route == "GET /scorecard":
        path = Path(__file__).parent / "scorecard.json"
        if not path.exists():
            return _response(404, {"error": "scorecard not bundled"})
        return _response(200, path.read_text())
    if route == "GET /bandit/curve":
        import base64

        path = Path(__file__).parent / "regret_curves.png"
        if not path.exists():
            return _response(404, {"error": "curve not bundled"})
        return {
            "statusCode": 200,
            "headers": {"content-type": "image/png"},
            "body": base64.b64encode(path.read_bytes()).decode(),
            "isBase64Encoded": True,
        }
    if route == "GET /":
        return _response(200, _frontend(), content_type="text/html; charset=utf-8")
    return _response(404, {"error": f"no route {route}"})
