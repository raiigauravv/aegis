import pytest
from aegis_core.models import TraceEvent, new_ticket_id
from pydantic import ValidationError


def test_trace_event_is_frozen() -> None:
    event = TraceEvent(ticket_id="tkt_1", service="intake_router", step="validate")
    with pytest.raises(ValidationError):
        event.step = "mutated"  # type: ignore[misc]


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        TraceEvent(ticket_id="tkt_1", service="s", step="v", surprise="x")  # type: ignore[call-arg]


def test_ticket_id_format() -> None:
    tid = new_ticket_id()
    assert tid.startswith("tkt_") and len(tid) == 16
