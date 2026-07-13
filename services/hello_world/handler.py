"""Phase-1 hello-world Lambda: proves the deploy pipeline and the shared
aegis_core package work end-to-end behind a Function URL."""

import json
from typing import Any

from aegis_core.config import settings
from aegis_core.models import new_ticket_id
from aegis_core.tracing import get_logger, traced_step

logger = get_logger("hello_world")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    ticket_id = new_ticket_id()
    with traced_step(logger, ticket_id=ticket_id, step="hello"):
        body = {
            "message": "AEGIS is alive",
            "ticket_id": ticket_id,
            "env": settings().env,
        }
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }
