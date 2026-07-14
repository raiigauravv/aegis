"""Classical extraction path: pdfplumber for born-digital PDFs, Tesseract OCR
for images and scanned pages. method="ocr" | "pdf_text" recorded for the
Phase-3 benchmark. The multimodal (Nova Lite) path is PENDING BEDROCK; the
routing rule between the two gets encoded once both columns are measured.

After extraction the ticket rejoins the text flow via the enrich queue.
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

logger = get_logger("extract_text")

_s3 = None
_sqs = None


def extract_pdf(path: Path) -> tuple[str, str, float]:
    """Returns (text, method, confidence)."""
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    text = "\n".join(pages).strip()
    if len(text) >= 40:  # born-digital: real text layer present
        return text, "pdf_text", 1.0
    # scanned PDF: rasterize and OCR
    from pdf2image import convert_from_path
    from pytesseract import image_to_data

    words, confs = [], []
    for image in convert_from_path(str(path), dpi=200):
        data = image_to_data(image, output_type="dict")
        for w, c in zip(data["text"], data["conf"], strict=True):
            if w.strip() and float(c) > 0:
                words.append(w)
                confs.append(float(c))
    return " ".join(words), "ocr", round(sum(confs) / len(confs) / 100, 3) if confs else 0.0


def extract_image(path: Path) -> tuple[str, str, float]:
    from PIL import Image
    from pytesseract import image_to_data

    data = image_to_data(Image.open(path), output_type="dict")
    words, confs = [], []
    for w, c in zip(data["text"], data["conf"], strict=True):
        if w.strip() and float(c) > 0:
            words.append(w)
            confs.append(float(c))
    return " ".join(words), "ocr", round(sum(confs) / len(confs) / 100, 3) if confs else 0.0


def extract_ticket(ticket_id: str) -> None:
    global _s3, _sqs
    start = time.perf_counter()
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(f"ticket {ticket_id} not found")
    meta = ticket["meta"]
    source = meta.get("source") or {}
    if "bucket" not in source:
        raise ValueError(f"ticket {ticket_id} has no s3 source")

    if _s3 is None:
        _s3 = boto3.client("s3")
    local = Path("/tmp") / Path(source["key"]).name
    _s3.download_file(source["bucket"], source["key"], str(local))

    if meta.get("modality") == "pdf":
        text, method, confidence = extract_pdf(local)
    else:
        text, method, confidence = extract_image(local)
    local.unlink(missing_ok=True)
    if not text.strip():
        raise ValueError(f"ticket {ticket_id}: extraction produced no text")

    store.update_meta(
        ticket_id,
        {"text": text[:10_000], "status": TicketStatus.RECEIVED},
    )
    latency = round((time.perf_counter() - start) * 1000, 2)
    store.append_trace(
        TraceEvent(
            ticket_id=ticket_id,
            service="extract_text",
            step="extract",
            latency_ms=latency,
            detail={"method": method, "confidence": str(confidence), "chars": str(len(text))},
        )
    )
    if _sqs is None:
        _sqs = boto3.client("sqs")
    _sqs.send_message(
        QueueUrl=os.environ["ENRICH_QUEUE_URL"],
        MessageBody=json.dumps({"ticket_id": ticket_id}),
    )
    logger.info("extracted", extra={"ticket_id": ticket_id, "step": "extract", "latency_ms": latency})


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures = []
    for record in event.get("Records", []):
        try:
            extract_ticket(json.loads(record["body"])["ticket_id"])
        except Exception:
            logger.error(
                "extract failed",
                extra={"step": "extract", "detail": {"messageId": record.get("messageId", "?")}},
                exc_info=True,
            )
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
