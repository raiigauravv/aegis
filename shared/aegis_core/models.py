"""Typed inter-service contracts. Every message that crosses a service boundary
is defined here, once. Phase 2+ adds TicketCreated, ExtractedContent, TriageDecision, etc.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _now() -> datetime:
    return datetime.now(UTC)


def new_ticket_id() -> str:
    return f"tkt_{uuid4().hex[:12]}"


class Modality(StrEnum):
    TEXT = "text"
    PDF = "pdf"
    IMAGE = "image"
    AUDIO = "audio"


class AegisModel(BaseModel):
    """Base for all contracts: immutable, no silent extra fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class TraceEvent(AegisModel):
    """One step in a ticket's decision chain. Written to DynamoDB as TRACE#<ts>."""

    ticket_id: str
    service: str
    step: str
    latency_ms: float | None = None
    detail: dict[str, str] = Field(default_factory=dict)
    at: datetime = Field(default_factory=_now)
