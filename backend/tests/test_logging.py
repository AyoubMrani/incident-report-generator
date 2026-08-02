"""
tests/test_logging.py — the service must be able to explain itself.

The privacy rule is the one that matters most here: this platform runs
on-premise because the incident data must not leave the company, so a log line
that echoed a question, a report body, or an answer would defeat the point.
These tests pin the format and the timing helper; the discipline of logging
identifiers rather than payloads is enforced by review, but `log_duration` is
built so the easy path stays safe.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.shared.logging import JsonFormatter, configure_logging, log_duration


def _record(**kwargs) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg=kwargs.pop("msg", "hello"), args=(), exc_info=None,
    )
    for key, value in kwargs.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_one_object_per_line():
    line = JsonFormatter().format(_record())
    payload = json.loads(line)

    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello"
    assert "\n" not in line


def test_json_formatter_merges_extra_fields():
    """Structured fields are what make logs queryable in a collector."""
    payload = json.loads(JsonFormatter().format(
        _record(event="kb_indexed", files=69, duration_ms=1200)
    ))

    assert payload["event"] == "kb_indexed"
    assert payload["files"] == 69
    assert payload["duration_ms"] == 1200


def test_json_formatter_does_not_leak_internal_record_attributes():
    payload = json.loads(JsonFormatter().format(_record()))
    for noisy in ("args", "msg", "pathname", "levelno", "exc_info"):
        assert noisy not in payload


def test_configure_logging_is_idempotent():
    """It runs in the lifespan, which tests re-enter repeatedly."""
    configure_logging()
    first = len(logging.getLogger().handlers)
    configure_logging()

    assert len(logging.getLogger().handlers) == first == 1


def test_configure_logging_honours_log_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_logging()
    assert logging.getLogger().level == logging.WARNING

    monkeypatch.setenv("LOG_LEVEL", "INFO")
    configure_logging()


def test_configure_logging_json_format(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    configure_logging()
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, JsonFormatter)

    monkeypatch.delenv("LOG_FORMAT")
    configure_logging()


def test_log_duration_reports_success(caplog):
    logger = logging.getLogger("app.test.duration")
    with caplog.at_level(logging.INFO, logger="app.test.duration"):
        with log_duration(logger, "retrieval", top_k=5):
            pass

    record = caplog.records[-1]
    assert record.event == "retrieval"
    assert record.ok is True
    assert record.top_k == 5
    assert record.duration_ms >= 0


def test_log_duration_reports_and_reraises_failures(caplog):
    """A swallowed error is the thing this whole module exists to prevent."""
    logger = logging.getLogger("app.test.duration")
    with caplog.at_level(logging.WARNING, logger="app.test.duration"):
        with pytest.raises(ValueError, match="boom"):
            with log_duration(logger, "retrieval"):
                raise ValueError("boom")

    record = caplog.records[-1]
    assert record.ok is False
    assert record.levelname == "WARNING"
