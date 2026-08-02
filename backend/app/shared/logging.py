"""
shared/logging.py — one place to configure how the service talks about itself.

The platform previously had no logging at all: thirteen `except Exception`
blocks swallowed their error and returned a fallback, which is correct
behaviour for keeping the service up but leaves nobody able to answer "why did
that answer look wrong at 14:20?". These helpers make failures observable
without changing that resilience.

Format is chosen by LOG_FORMAT:
  text  (default) human-readable, for local work and `docker compose logs`
  json             one object per line, for a log collector

Level comes from LOG_LEVEL (default INFO).

Never log the contents of a report, a question, or an answer: this runs on
customer incident data on-premise precisely because that data must not leave
the company. Log identifiers, counts, timings and outcomes — never payloads.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import contextmanager


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with any `extra=` fields merged in."""

    _RESERVED = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Install the root handler. Idempotent: safe to call from the lifespan."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    fmt = os.getenv("LOG_FORMAT", "text").lower()

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
    root.addHandler(handler)
    root.setLevel(getattr(logging, level, logging.INFO))

    # uvicorn installs its own handlers; let them propagate to ours instead so
    # everything comes out in one format.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True

    # httpx logs every outbound request at INFO, which is noise here.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


@contextmanager
def log_duration(logger: logging.Logger, event: str, **fields):
    """Time a block and log how it went — including when it raises.

    Emits one record on success and one on failure, so a slow stage and a
    failing stage are both visible without the caller writing try/except.
    """
    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        logger.warning(
            "%s failed after %.0fms: %s", event,
            (time.perf_counter() - started) * 1000, exc,
            extra={"event": event, "ok": False,
                   "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                   **fields},
        )
        raise
    logger.info(
        "%s in %.0fms", event, (time.perf_counter() - started) * 1000,
        extra={"event": event, "ok": True,
               "duration_ms": round((time.perf_counter() - started) * 1000, 1),
               **fields},
    )
