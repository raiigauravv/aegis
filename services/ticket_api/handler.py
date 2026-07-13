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


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    route = event.get("routeKey", "")
    if route == "POST /tickets":
        return _post_ticket(event)
    if route == "GET /tickets/{id}":
        return _get_ticket(event["pathParameters"]["id"])
    if route == "GET /":
        return _response(200, _frontend(), content_type="text/html; charset=utf-8")
    return _response(404, {"error": f"no route {route}"})
