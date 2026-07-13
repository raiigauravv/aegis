"""Structured JSON logging for every AEGIS service.

Convention (Phase 1, step 5): every log line carries ticket_id, service, step,
and latency_ms so CloudWatch Logs Insights can reconstruct any ticket's timeline with
one query. Use `traced_step` around any unit of work worth timing.
"""

import json
import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

_RESERVED = {"ticket_id", "service", "step", "latency_ms"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "message": record.getMessage(),
            "ticket_id": getattr(record, "ticket_id", None),
            "service": getattr(record, "service", None),
            "step": getattr(record, "step", None),
            "latency_ms": getattr(record, "latency_ms", None),
        }
        extra = getattr(record, "detail", None)
        if extra:
            line["detail"] = extra
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


class _MergingAdapter(logging.LoggerAdapter[logging.Logger]):
    """Unlike the stock LoggerAdapter, merges per-call `extra` with the adapter's
    own instead of discarding it — otherwise ticket_id/step/latency_ms vanish."""

    def process(self, msg: Any, kwargs: Any) -> tuple[Any, Any]:
        kwargs["extra"] = {**(self.extra or {}), **(kwargs.get("extra") or {})}
        return msg, kwargs


def get_logger(service: str) -> logging.LoggerAdapter[logging.Logger]:
    """One logger per service; `service` is stamped on every line."""
    logger = logging.getLogger(f"aegis.{service}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return _MergingAdapter(logger, {"service": service})


@contextmanager
def traced_step(
    logger: logging.LoggerAdapter[logging.Logger],
    ticket_id: str,
    step: str,
    **detail: str,
) -> Iterator[None]:
    """Log start/end of a step with wall-clock latency_ms; re-raises on failure."""
    start = time.perf_counter()
    try:
        yield
    except Exception:
        latency = (time.perf_counter() - start) * 1000
        logger.error(
            f"{step} failed",
            extra={"ticket_id": ticket_id, "step": step, "latency_ms": round(latency, 2), "detail": detail},
            exc_info=True,
        )
        raise
    latency = (time.perf_counter() - start) * 1000
    logger.info(
        f"{step} ok",
        extra={"ticket_id": ticket_id, "step": step, "latency_ms": round(latency, 2), "detail": detail},
    )
