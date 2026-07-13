"""Single-table DynamoDB persistence for tickets.

Layout (documented in docs/architecture.md):
    PK = TICKET#<ticket_id>
    SK = META                      -> TicketMeta (current state, one item)
    SK = TRACE#<iso-ts>#<nonce>    -> TraceEvent (append-only decision chain)
    SK = FEEDBACK#<iso-ts>         -> Phase 7/8

Writes are idempotent: META uses a conditional put keyed on the ticket_id, so
SQS at-least-once redelivery cannot create duplicates.
"""

import os
from decimal import Decimal
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

from aegis_core.models import TicketMeta, TraceEvent

_table = None


def table() -> Any:
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


def _pk(ticket_id: str) -> str:
    return f"TICKET#{ticket_id}"


def put_ticket_meta(meta: TicketMeta) -> bool:
    """Create the META item. Returns False if the ticket already exists (idempotent replay)."""
    item = {
        "PK": _pk(meta.ticket_id),
        "SK": "META",
        **meta.model_dump(mode="json"),
    }
    try:
        table().put_item(Item=item, ConditionExpression="attribute_not_exists(SK)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
    return True


def append_trace(event: TraceEvent) -> None:
    item: dict[str, Any] = {
        "PK": _pk(event.ticket_id),
        "SK": f"TRACE#{event.at.isoformat()}#{uuid4().hex[:6]}",
        **event.model_dump(mode="json"),
    }
    if event.latency_ms is not None:
        item["latency_ms"] = Decimal(str(round(event.latency_ms, 3)))
    table().put_item(Item=item)


def get_ticket(ticket_id: str) -> dict[str, Any] | None:
    """Return {'meta': ..., 'trace': [...]} or None if the ticket doesn't exist."""
    resp = table().query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": _pk(ticket_id)},
    )
    meta, trace = None, []
    for item in resp.get("Items", []):
        item.pop("PK", None)
        sk = str(item.pop("SK", ""))
        if "latency_ms" in item and isinstance(item["latency_ms"], Decimal):
            item["latency_ms"] = float(item["latency_ms"])
        if sk == "META":
            meta = item
        elif sk.startswith("TRACE#"):
            trace.append(item)
    if meta is None:
        return None
    trace.sort(key=lambda t: str(t.get("at", "")))
    return {"meta": meta, "trace": trace}
