import json
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from aegis_core import store
from aegis_core.models import TicketSubmission
from moto import mock_aws

from .handler import lambda_handler


@pytest.fixture()
def tickets_table(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
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


def _sqs_event(*bodies: str) -> dict[str, Any]:
    return {"Records": [{"messageId": f"m{i}", "body": b} for i, b in enumerate(bodies)]}


def test_api_submission_creates_meta_and_trace(tickets_table: None) -> None:
    sub = TicketSubmission(ticket_id="tkt_api1", text="my app crashes")
    result = lambda_handler(_sqs_event(sub.model_dump_json()), None)
    assert result["batchItemFailures"] == []
    ticket = store.get_ticket("tkt_api1")
    assert ticket is not None
    assert ticket["meta"]["status"] == "received"
    assert ticket["trace"][0]["step"] == "ingest"


def test_duplicate_delivery_is_idempotent(tickets_table: None) -> None:
    sub = TicketSubmission(ticket_id="tkt_dup", text="hello")
    lambda_handler(_sqs_event(sub.model_dump_json()), None)
    lambda_handler(_sqs_event(sub.model_dump_json()), None)
    ticket = store.get_ticket("tkt_dup")
    assert ticket is not None
    assert len(ticket["trace"]) == 1  # replay added nothing


def test_s3_event_parks_ticket_awaiting_extraction(tickets_table: None) -> None:
    s3_event = json.dumps(
        {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "intake"},
                        "object": {"key": "docs/invoice+1.pdf"},
                    }
                }
            ]
        }
    )
    result = lambda_handler(_sqs_event(s3_event), None)
    assert result["batchItemFailures"] == []
    # find the created ticket via a scan of the mock table
    items = store.table().scan()["Items"]
    metas = [i for i in items if i["SK"] == "META"]
    assert len(metas) == 1
    assert metas[0]["status"] == "awaiting_extraction"
    assert metas[0]["modality"] == "pdf"
    assert metas[0]["source"]["key"] == "docs/invoice 1.pdf"  # url-decoded


def test_s3_test_event_is_ignored(tickets_table: None) -> None:
    result = lambda_handler(_sqs_event(json.dumps({"Event": "s3:TestEvent"})), None)
    assert result["batchItemFailures"] == []
    assert store.table().scan()["Items"] == []


def test_malformed_record_reports_failure(tickets_table: None) -> None:
    good = TicketSubmission(ticket_id="tkt_ok", text="fine").model_dump_json()
    result = lambda_handler(_sqs_event("not json", good), None)
    assert result["batchItemFailures"] == [{"itemIdentifier": "m0"}]
    assert store.get_ticket("tkt_ok") is not None  # good record still processed
