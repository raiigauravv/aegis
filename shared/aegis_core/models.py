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


class Channel(StrEnum):
    API = "api"
    S3 = "s3"


class TicketStatus(StrEnum):
    RECEIVED = "received"
    AWAITING_EXTRACTION = "awaiting_extraction"  # file dropped, Phase 3 extracts
    AWAITING_TRANSCRIPTION = "awaiting_transcription"  # voice note, whisper path
    ENRICHED = "enriched"  # language/sentiment/redaction done
    AWAITING_APPROVAL = "awaiting_approval"  # risk tier >= 3, human queue
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


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


class TicketSubmission(AegisModel):
    """What ticket_api enqueues to SQS for the intake_router."""

    ticket_id: str
    text: str = Field(min_length=1, max_length=10_000)
    subject: str | None = Field(default=None, max_length=200)
    channel: Channel = Channel.API
    submitted_at: datetime = Field(default_factory=_now)


class TicketMeta(AegisModel):
    """The META item for a ticket — its authoritative current state."""

    ticket_id: str
    status: TicketStatus
    channel: Channel
    modality: Modality
    subject: str | None = None
    text: str = ""
    source: dict[str, str] = Field(default_factory=dict)  # e.g. s3 bucket/key
    created_at: datetime = Field(default_factory=_now)
