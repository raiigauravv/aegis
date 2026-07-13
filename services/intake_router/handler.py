"""Consumes the ingest SQS queue and persists tickets.

Two message shapes arrive here:
  - TicketSubmission JSON from ticket_api (text tickets)
  - S3 event notifications from the intake bucket (file drops; extraction is Phase 3,
    so those tickets are parked in AWAITING_EXTRACTION)

Uses SQS partial-batch responses: only failed records are retried, and after the
redrive limit they land in the DLQ (alarmed).
"""

import json
import time
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote_plus

from aegis_core import store
from aegis_core.models import (
    Channel,
    Modality,
    TicketMeta,
    TicketStatus,
    TicketSubmission,
    TraceEvent,
    new_ticket_id,
)
from aegis_core.tracing import get_logger
from pydantic import ValidationError

logger = get_logger("intake_router")

_EXT_MODALITY = {
    ".pdf": Modality.PDF,
    ".png": Modality.IMAGE,
    ".jpg": Modality.IMAGE,
    ".jpeg": Modality.IMAGE,
    ".mp3": Modality.AUDIO,
    ".m4a": Modality.AUDIO,
    ".wav": Modality.AUDIO,
    ".ogg": Modality.AUDIO,
}


def _meta_from_submission(sub: TicketSubmission) -> TicketMeta:
    return TicketMeta(
        ticket_id=sub.ticket_id,
        status=TicketStatus.RECEIVED,
        channel=sub.channel,
        modality=Modality.TEXT,
        subject=sub.subject,
        text=sub.text,
    )


def _meta_from_s3_record(rec: dict[str, Any]) -> TicketMeta:
    bucket = rec["s3"]["bucket"]["name"]
    key = unquote_plus(rec["s3"]["object"]["key"])
    modality = _EXT_MODALITY.get(PurePosixPath(key).suffix.lower(), Modality.PDF)
    return TicketMeta(
        ticket_id=new_ticket_id(),
        status=TicketStatus.AWAITING_EXTRACTION,
        channel=Channel.S3,
        modality=modality,
        source={"bucket": bucket, "key": key},
    )


def _process_body(body: str) -> None:
    start = time.perf_counter()
    payload = json.loads(body)

    if "Records" in payload:  # S3 event notification (possibly several objects)
        metas = [_meta_from_s3_record(r) for r in payload["Records"] if "s3" in r]
    elif payload.get("Event") == "s3:TestEvent":  # S3 sends one on wiring; ignore
        return
    else:
        metas = [_meta_from_submission(TicketSubmission.model_validate(payload))]

    for meta in metas:
        created = store.put_ticket_meta(meta)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        if not created:  # SQS redelivery of an already-processed ticket
            logger.info(
                "duplicate delivery ignored",
                extra={
                    "ticket_id": meta.ticket_id,
                    "step": "ingest",
                    "latency_ms": latency_ms,
                },
            )
            continue
        store.append_trace(
            TraceEvent(
                ticket_id=meta.ticket_id,
                service="intake_router",
                step="ingest",
                latency_ms=latency_ms,
                detail={
                    "channel": meta.channel,
                    "modality": meta.modality,
                    "status": meta.status,
                },
            )
        )
        logger.info(
            "ticket ingested",
            extra={
                "ticket_id": meta.ticket_id,
                "step": "ingest",
                "latency_ms": latency_ms,
            },
        )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures = []
    for record in event.get("Records", []):
        try:
            _process_body(record["body"])
        except (ValidationError, json.JSONDecodeError, KeyError):
            # Malformed payloads will never succeed: let redrive move them to the DLQ.
            logger.error(
                "unprocessable record",
                extra={
                    "step": "ingest",
                    "detail": {"messageId": record.get("messageId", "?")},
                },
                exc_info=True,
            )
            failures.append({"itemIdentifier": record["messageId"]})
        except Exception:
            logger.error(
                "transient failure",
                extra={
                    "step": "ingest",
                    "detail": {"messageId": record.get("messageId", "?")},
                },
                exc_info=True,
            )
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
