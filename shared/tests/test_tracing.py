import json
import logging

import pytest

from aegis_core.tracing import JsonFormatter, get_logger, traced_step


@pytest.fixture()
def capture(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    lines: list[str] = []
    logger = get_logger("test_svc")
    handler = logger.logger.handlers[0]
    monkeypatch.setattr(handler, "emit", lambda record: lines.append(handler.format(record)))
    return lines


def test_log_line_is_json_with_required_keys(capture: list[str]) -> None:
    logger = get_logger("test_svc")
    with traced_step(logger, ticket_id="tkt_abc", step="validate"):
        pass
    line = json.loads(capture[-1])
    assert line["ticket_id"] == "tkt_abc"
    assert line["service"] == "test_svc"
    assert line["step"] == "validate"
    assert isinstance(line["latency_ms"], float)


def test_failed_step_logs_error_and_reraises(capture: list[str]) -> None:
    logger = get_logger("test_svc")
    with pytest.raises(ValueError), traced_step(logger, ticket_id="tkt_abc", step="boom"):
        raise ValueError("nope")
    line = json.loads(capture[-1])
    assert line["level"] == "ERROR"
    assert line["step"] == "boom"
    assert "ValueError" in line["exc"]


def test_formatter_handles_plain_record() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    line = json.loads(JsonFormatter().format(record))
    assert line["message"] == "hello"
    assert line["ticket_id"] is None
