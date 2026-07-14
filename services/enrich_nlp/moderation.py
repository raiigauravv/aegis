"""Moderation gate: screens outbound drafts BEFORE release.

Deployed as its own Lambda from the enrich_nlp image (CMD override) so it reuses
the Presidio stack. Three checks, all deterministic:

  1. PII leakage — re-run detection on the OUTPUT; any hit fails the draft
     (catches PII smuggled through retrieval or copied from context).
  2. Unsupported-claim heuristic — fact-bearing sentences (amounts, timelines,
     limits) must carry a citation marker [n]; uncited facts fail.
  3. Policy phrases — guarantees and legal/financial advice language fail.

Verdict + reasons are logged to the ticket trace: a blocked draft is an
auditable event, not a silent drop. Invoked by the Phase-6 state machine before
Approval-or-Send; callable directly: {"draft": ..., "ticket_id": ...}.
"""

import re
import time
from typing import Any

from aegis_core import store
from aegis_core.models import TraceEvent
from aegis_core.tracing import get_logger
from redactor import detect

logger = get_logger("moderation_gate")

_CITATION = re.compile(r"\[\d+\]")
_FACT_SIGNALS = re.compile(
    r"(\$\d|\d+ ?(?:business days?|days?|hours?|minutes?)\b|\d+%|limit|fee of|within \d+)",
    re.IGNORECASE,
)
_POLICY_PHRASES = (
    "we guarantee",
    "guaranteed",
    "you should sue",
    "legal advice",
    "cannot be hacked",
    "100% safe",
    "always approve",
)


def moderate(draft: str) -> dict[str, Any]:
    reasons: list[str] = []

    pii_hits = detect(draft)
    if pii_hits:
        reasons.append("pii_leakage: " + ", ".join(sorted({r.entity_type for r in pii_hits})))

    for sentence in re.split(r"(?<=[.!?])\s+", draft):
        if _FACT_SIGNALS.search(sentence) and not _CITATION.search(sentence):
            reasons.append(f"uncited_claim: {sentence.strip()[:80]}")

    lower = draft.lower()
    reasons.extend(f"policy_phrase: {p}" for p in _POLICY_PHRASES if p in lower)

    return {"pass": not reasons, "reasons": reasons}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    start = time.perf_counter()
    verdict = moderate(event["draft"])
    ticket_id = event.get("ticket_id")
    if ticket_id:
        store.append_trace(
            TraceEvent(
                ticket_id=ticket_id,
                service="moderation_gate",
                step="moderate",
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                detail={
                    "verdict": "pass" if verdict["pass"] else "fail",
                    "reasons": "; ".join(verdict["reasons"])[:400] or "none",
                },
            )
        )
    logger.info(
        "draft moderated",
        extra={
            "ticket_id": ticket_id or "n/a",
            "step": "moderate",
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "detail": {"verdict": "pass" if verdict["pass"] else "fail"},
        },
    )
    return verdict
