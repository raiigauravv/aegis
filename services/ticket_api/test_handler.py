import json
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from moto import mock_aws

from . import handler
from .handler import lambda_handler

Queue = tuple[Any, str]


@pytest.fixture()
def queue(monkeypatch: pytest.MonkeyPatch) -> Iterator[Queue]:
    with mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-1")
        url = sqs.create_queue(QueueName="test-ingest")["QueueUrl"]
        monkeypatch.setenv("QUEUE_URL", url)
        monkeypatch.setattr(handler, "_sqs", None)
        yield sqs, url
        handler._sqs = None


def test_post_ticket_enqueues_submission(queue: Queue) -> None:
    sqs, url = queue
    resp = lambda_handler(
        {
            "routeKey": "POST /tickets",
            "body": json.dumps({"text": "help", "subject": "login"}),
        },
        None,
    )
    assert resp["statusCode"] == 202
    ticket_id = json.loads(resp["body"])["ticket_id"]
    msg = json.loads(sqs.receive_message(QueueUrl=url)["Messages"][0]["Body"])
    assert msg["ticket_id"] == ticket_id
    assert msg["subject"] == "login"


def test_post_rejects_empty_text(queue: Queue) -> None:
    resp = lambda_handler({"routeKey": "POST /tickets", "body": json.dumps({"text": ""})}, None)
    assert resp["statusCode"] == 422


def test_post_rejects_unknown_fields(queue: Queue) -> None:
    resp = lambda_handler(
        {
            "routeKey": "POST /tickets",
            "body": json.dumps({"text": "hi", "admin": True}),
        },
        None,
    )
    assert resp["statusCode"] == 422  # extra=forbid on the contract


def test_post_rejects_non_json(queue: Queue) -> None:
    resp = lambda_handler({"routeKey": "POST /tickets", "body": "{{{"}, None)
    assert resp["statusCode"] == 400


def test_unknown_route_404s() -> None:
    resp = lambda_handler({"routeKey": "GET /nope"}, None)
    assert resp["statusCode"] == 404
