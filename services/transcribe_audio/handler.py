"""Voice-note path: faster-whisper (small, int8) transcription.

Consumes {ticket_id} from the transcribe queue, downloads the audio object the
ticket points at, transcribes, then forwards the ticket into the same enrichment
flow as text tickets (transcript is redacted there BEFORE persistence — the
transcript we store here is replaced by enrich_nlp's redacted version).
"""

import json
import os
import time
from pathlib import Path
from typing import Any

import boto3
from aegis_core import store
from aegis_core.models import TicketStatus, TraceEvent
from aegis_core.tracing import get_logger
from faster_whisper import WhisperModel

logger = get_logger("transcribe_audio")

_model: WhisperModel | None = None
_s3 = None
_sqs = None


def model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(os.environ.get("MODEL_DIR", "/opt/whisper-small"), compute_type="int8")
    return _model


def transcribe_ticket(ticket_id: str) -> None:
    global _s3, _sqs
    start = time.perf_counter()
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(f"ticket {ticket_id} not found")
    source = ticket["meta"].get("source") or {}
    if "bucket" not in source:
        raise ValueError(f"ticket {ticket_id} has no s3 source")

    if _s3 is None:
        _s3 = boto3.client("s3")
    local = Path("/tmp") / Path(source["key"]).name
    _s3.download_file(source["bucket"], source["key"], str(local))

    segments, info = model().transcribe(str(local), beam_size=1)
    transcript = " ".join(seg.text.strip() for seg in segments).strip()
    local.unlink(missing_ok=True)
    if not transcript:
        raise ValueError(f"ticket {ticket_id}: empty transcript")

    store.update_meta(
        ticket_id,
        {
            "text": transcript,
            "transcript_language": info.language,
            "status": TicketStatus.RECEIVED,  # rejoins the text flow
        },
    )
    latency = round((time.perf_counter() - start) * 1000, 2)
    store.append_trace(
        TraceEvent(
            ticket_id=ticket_id,
            service="transcribe_audio",
            step="transcribe",
            latency_ms=latency,
            detail={
                "language": info.language,
                "duration_s": str(round(info.duration, 1)),
                "chars": str(len(transcript)),
            },
        )
    )
    if _sqs is None:
        _sqs = boto3.client("sqs")
    _sqs.send_message(
        QueueUrl=os.environ["ENRICH_QUEUE_URL"],
        MessageBody=json.dumps({"ticket_id": ticket_id}),
    )
    logger.info(
        "transcribed",
        extra={"ticket_id": ticket_id, "step": "transcribe", "latency_ms": latency},
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures = []
    for record in event.get("Records", []):
        try:
            transcribe_ticket(json.loads(record["body"])["ticket_id"])
        except Exception:
            logger.error(
                "transcribe failed",
                extra={"step": "transcribe", "detail": {"messageId": record.get("messageId", "?")}},
                exc_info=True,
            )
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
