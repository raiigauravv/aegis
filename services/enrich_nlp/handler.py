"""Enrichment stage: language detection, sentiment, PII redaction, risk tier.

Consumes {ticket_id} messages from the enrich queue. Redaction happens BEFORE any
derived text is persisted: META gets redacted_text only; the reversible mapping
goes to the fenced-off pii-map table (this service is its only writer).

Risk tier is a deterministic keyword/sentiment floor for the approval workflow.
The LLM triage agent (Nova Micro) replaces it as the primary signal once the
Bedrock quota case resolves — the floor stays as a governance backstop.

Intent classification: PENDING BEDROCK (zero-shot Nova Micro, fixed label set).
"""

import json
import os
import time
from typing import Any

import boto3
from aegis_core import store
from aegis_core.models import TicketStatus, TraceEvent
from aegis_core.tracing import get_logger
from langdetect import DetectorFactory
from langdetect import detect as detect_language
from redactor import redact  # bundled alongside in the image
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

DetectorFactory.seed = 0  # deterministic langdetect
logger = get_logger("enrich_nlp")
_vader = SentimentIntensityAnalyzer()
_dynamo = None

TIER3_KEYWORDS = (
    "fraud",
    "stolen",
    "unauthorized",
    "lawyer",
    "legal action",
    "lawsuit",
    "close my account",
    "wire transfer",
    "police",
    "compensation",
    "sue",
)


def _pii_table() -> Any:
    global _dynamo
    if _dynamo is None:
        _dynamo = boto3.resource("dynamodb").Table(os.environ["PII_TABLE_NAME"])
    return _dynamo


def risk_tier(text: str, sentiment: float) -> int:
    lower = text.lower()
    if any(k in lower for k in TIER3_KEYWORDS):
        return 3
    if sentiment <= -0.6:
        return 2
    return 1


def enrich_ticket(ticket_id: str) -> None:
    start = time.perf_counter()
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(f"ticket {ticket_id} not found")
    text = ticket["meta"].get("text") or ""
    if not text:
        raise ValueError(f"ticket {ticket_id} has no text to enrich")

    try:
        language = detect_language(text)
    except Exception:
        language = "unknown"
    sentiment = _vader.polarity_scores(text)["compound"]
    redacted, mapping = redact(text)
    tier = risk_tier(text, sentiment)

    if mapping:
        _pii_table().put_item(Item={"PK": f"TICKET#{ticket_id}", "mapping": mapping})

    status = TicketStatus.AWAITING_APPROVAL if tier >= 3 else TicketStatus.ENRICHED
    store.update_meta(
        ticket_id,
        {
            "text": redacted,  # raw text is replaced; original recoverable via pii-map only
            "language": language,
            "sentiment": str(round(sentiment, 3)),
            "pii_found": len(mapping),
            "risk_tier": tier,
            "intent": "pending_bedrock",
            "status": status,
        },
    )
    latency = round((time.perf_counter() - start) * 1000, 2)
    store.append_trace(
        TraceEvent(
            ticket_id=ticket_id,
            service="enrich_nlp",
            step="enrich",
            latency_ms=latency,
            detail={
                "language": language,
                "sentiment": str(round(sentiment, 3)),
                "pii_redacted": str(len(mapping)),
                "risk_tier": str(tier),
                "status": status,
            },
        )
    )
    logger.info("enriched", extra={"ticket_id": ticket_id, "step": "enrich", "latency_ms": latency})


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures = []
    for record in event.get("Records", []):
        try:
            enrich_ticket(json.loads(record["body"])["ticket_id"])
        except Exception:
            logger.error(
                "enrich failed",
                extra={"step": "enrich", "detail": {"messageId": record.get("messageId", "?")}},
                exc_info=True,
            )
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
