"""Structured logging tests (SPEC §11)."""

from __future__ import annotations

import json
import re

from agentos.observability import _iso_now, log_event


def test_log_event_emits_valid_json(capsys):
    log_event(kind="cell", namespace="ns", turn_id="t_abc", cell="echo", version="1.0.0")
    line = capsys.readouterr().out.strip()
    event = json.loads(line)
    assert event["kind"] == "cell"
    assert event["namespace"] == "ns"
    assert event["turn_id"] == "t_abc"
    assert event["cell"] == "echo"
    assert "ts" in event


def test_optional_fields_only_when_present(capsys):
    log_event(kind="kernel", namespace="*", turn_id="-")
    event = json.loads(capsys.readouterr().out.strip())
    assert "duration_ms" not in event
    assert "error" not in event


def test_duration_and_error_included(capsys):
    log_event(kind="hook", namespace="ns", turn_id="t1", duration_ms=12, error="boom")
    event = json.loads(capsys.readouterr().out.strip())
    assert event["duration_ms"] == 12
    assert event["error"] == "boom"


def test_iso_now_format():
    ts = _iso_now()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", ts)
