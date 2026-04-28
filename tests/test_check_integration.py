"""check.run() の統合テスト（HTTP モック）。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from scripts import check
from scripts.fetcher import ENDPOINT
from scripts.notifier import NTFY_BASE
from scripts.state import JST
from tests.conftest import load_fixture

TOPIC = "test-integration-topic"
NOW = datetime(2026, 4, 28, 6, 5, 12, tzinfo=JST)  # 07:00 ヘルスチェック時刻より前


def _args(state_path: Path, dry_run: bool = False):
    import argparse

    return argparse.Namespace(
        dry_run=dry_run,
        target_date="2026-05-08",
        state_path=state_path,
    )


def test_first_run_full_writes_state_no_notification(
    tmp_path, monkeypatch, requests_mock
):
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    requests_mock.post(ENDPOINT, json=load_fixture("full.json"))
    requests_mock.post(NTFY_BASE, json={"id": "x"})

    state_path = tmp_path / "state.json"
    rc = check.run(_args(state_path), now=NOW)
    assert rc == 0

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["last_status"] == "full"
    assert data["consecutive_errors"] == 0

    ntfy_calls = [c for c in requests_mock.request_history if c.url.startswith(NTFY_BASE)]
    assert ntfy_calls == []


def test_full_to_available_sends_urgent(
    tmp_path, monkeypatch, requests_mock
):
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    requests_mock.post(ENDPOINT, json=load_fixture("available.json"))
    requests_mock.post(NTFY_BASE, json={"id": "x"})

    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "target_date": "2026-05-08",
                "last_status": "full",
                "last_check_at": "2026-04-27T07:05:12+09:00",
                "last_change_at": "2026-04-27T07:05:12+09:00",
                "consecutive_errors": 0,
                "last_health_check_at": None,
            }
        ),
        encoding="utf-8",
    )

    rc = check.run(_args(state_path), now=NOW)
    assert rc == 0

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["last_status"] == "available"

    ntfy_calls = [c for c in requests_mock.request_history if c.url.startswith(NTFY_BASE)]
    assert len(ntfy_calls) == 1
    body = ntfy_calls[0].json()
    assert body["priority"] == 5
    assert body["topic"] == TOPIC


def test_dry_run_does_not_post_to_ntfy(
    tmp_path, monkeypatch, requests_mock
):
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    requests_mock.post(ENDPOINT, json=load_fixture("available.json"))
    requests_mock.post(NTFY_BASE, json={"id": "x"})

    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "target_date": "2026-05-08",
                "last_status": "full",
                "consecutive_errors": 0,
            }
        ),
        encoding="utf-8",
    )

    rc = check.run(_args(state_path, dry_run=True), now=NOW)
    assert rc == 0

    ntfy_calls = [c for c in requests_mock.request_history if c.url.startswith(NTFY_BASE)]
    assert ntfy_calls == []
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["last_status"] == "available"


def test_fetch_failure_increments_consecutive_errors(
    tmp_path, monkeypatch, requests_mock
):
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    requests_mock.post(ENDPOINT, status_code=500)
    requests_mock.post(NTFY_BASE, json={"id": "x"})

    state_path = tmp_path / "state.json"
    rc = check.run(_args(state_path), now=NOW)
    assert rc == 0

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["consecutive_errors"] == 1
    assert data["last_status"] == "unknown"


def test_third_consecutive_error_triggers_high_alert(
    tmp_path, monkeypatch, requests_mock
):
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    requests_mock.post(ENDPOINT, status_code=500)
    requests_mock.post(NTFY_BASE, json={"id": "x"})

    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "target_date": "2026-05-08",
                "last_status": "full",
                "consecutive_errors": 2,
            }
        ),
        encoding="utf-8",
    )

    rc = check.run(_args(state_path), now=NOW)
    assert rc == 0

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["last_status"] == "error"
    assert data["consecutive_errors"] == 0

    ntfy_calls = [c for c in requests_mock.request_history if c.url.startswith(NTFY_BASE)]
    assert len(ntfy_calls) == 1
    assert ntfy_calls[0].json()["priority"] == 4


def test_target_date_itself_exits_early(
    tmp_path, monkeypatch, requests_mock
):
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    state_path = tmp_path / "state.json"
    target_day = datetime(2026, 5, 8, 7, 5, 12, tzinfo=JST)
    rc = check.run(_args(state_path), now=target_day)
    assert rc == 0
    assert not state_path.exists()
    assert requests_mock.call_count == 0


def test_last_day_5_7_still_runs(
    tmp_path, monkeypatch, requests_mock
):
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    requests_mock.post(ENDPOINT, json=load_fixture("full.json"))
    requests_mock.post(NTFY_BASE, json={"id": "x"})

    state_path = tmp_path / "state.json"
    last_day = datetime(2026, 5, 7, 23, 5, 0, tzinfo=JST)
    rc = check.run(_args(state_path), now=last_day)
    assert rc == 0
    assert state_path.exists()


def test_daily_health_check_at_7am(
    tmp_path, monkeypatch, requests_mock
):
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    requests_mock.post(ENDPOINT, json=load_fixture("full.json"))
    requests_mock.post(NTFY_BASE, json={"id": "x"})

    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "target_date": "2026-05-08",
                "last_status": "full",
                "consecutive_errors": 0,
                "last_health_check_at": None,
            }
        ),
        encoding="utf-8",
    )

    morning = datetime(2026, 4, 30, 7, 5, 0, tzinfo=JST)
    rc = check.run(_args(state_path), now=morning)
    assert rc == 0

    ntfy_calls = [c for c in requests_mock.request_history if c.url.startswith(NTFY_BASE)]
    assert len(ntfy_calls) == 1
    body = ntfy_calls[0].json()
    assert body["priority"] == 2
    assert "稼働中" in body["title"]

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["last_health_check_at"] is not None
