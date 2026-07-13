import boto3
import pytest
from aegis_core import store
from aegis_core.models import Channel, Modality, TicketMeta, TicketStatus, TraceEvent
from moto import mock_aws


@pytest.fixture()
def tickets_table(monkeypatch: pytest.MonkeyPatch):
    with mock_aws():
        monkeypatch.setenv("TABLE_NAME", "test-tickets")
        monkeypatch.setattr(store, "_table", None)
        boto3.resource("dynamodb", region_name="us-east-1").create_table(
            TableName="test-tickets",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield
        store._table = None


def _meta(ticket_id: str = "tkt_1") -> TicketMeta:
    return TicketMeta(
        ticket_id=ticket_id,
        status=TicketStatus.RECEIVED,
        channel=Channel.API,
        modality=Modality.TEXT,
        text="hello",
    )


def test_meta_put_is_idempotent(tickets_table: None) -> None:
    assert store.put_ticket_meta(_meta()) is True
    assert store.put_ticket_meta(_meta()) is False  # replay -> no duplicate


def test_get_ticket_roundtrip_with_trace(tickets_table: None) -> None:
    store.put_ticket_meta(_meta())
    store.append_trace(TraceEvent(ticket_id="tkt_1", service="intake_router", step="ingest", latency_ms=12.5))
    ticket = store.get_ticket("tkt_1")
    assert ticket is not None
    assert ticket["meta"]["status"] == "received"
    assert len(ticket["trace"]) == 1
    assert ticket["trace"][0]["latency_ms"] == pytest.approx(12.5)


def test_get_missing_ticket_returns_none(tickets_table: None) -> None:
    assert store.get_ticket("tkt_nope") is None
