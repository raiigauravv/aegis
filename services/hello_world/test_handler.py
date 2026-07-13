import json

from .handler import lambda_handler


def test_returns_200_with_ticket_id() -> None:
    response = lambda_handler({}, None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["message"] == "AEGIS is alive"
    assert body["ticket_id"].startswith("tkt_")
