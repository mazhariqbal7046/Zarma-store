"""Small, dependency-free structured logging setup for production hosting."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from threading import Lock
from typing import Any


request_id_context: ContextVar[str] = ContextVar("zarma_request_id", default="-")
_metrics_lock = Lock()
_metrics: dict[str, Any] = {
    "requests_total": 0,
    "responses_4xx": 0,
    "responses_5xx": 0,
    "duration_ms_total": 0.0,
}


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line without serializing secrets."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        for field in ("method", "route", "status_code", "duration_ms", "exception_type"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Configure a single structured stream suitable for Render log ingestion."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # httpx INFO messages include full URLs and query filters; keep those out of logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def record_request(*, status_code: int, duration_ms: float) -> None:
    """Record aggregate operational metrics without retaining request data."""

    with _metrics_lock:
        _metrics["requests_total"] += 1
        _metrics["duration_ms_total"] += duration_ms
        if 400 <= status_code < 500:
            _metrics["responses_4xx"] += 1
        elif status_code >= 500:
            _metrics["responses_5xx"] += 1


def metrics_snapshot() -> dict[str, Any]:
    with _metrics_lock:
        snapshot = dict(_metrics)
    requests = snapshot["requests_total"]
    snapshot["duration_ms_average"] = round(
        snapshot["duration_ms_total"] / requests, 2
    ) if requests else 0.0
    snapshot.pop("duration_ms_total", None)
    return snapshot

