from datetime import datetime, timedelta, timezone

import pytest

from scripts.state import (
    JST,
    Decision,
    Notification,
    NotificationKind,
    State,
    decide,
    load_state,
    mark_health_check_sent,
    save_state,
    should_send_health_check,
)

NOW = datetime(2026, 4, 28, 7, 5, 12, tzinfo=JST)
TARGET = "2026-05-08"


def _state(status="unknown", consec=0, last_change=None, last_health=None):
    return State(
        target_date=TARGET,
        last_status=status,
        last_check_at=None,
        last_change_at=last_change,
        consecutive_errors=consec,
        last_health_check_at=last_health,
    )


def test_unknown_to_full_silent():
    d = decide(_state("unknown"), "full", NOW)
    assert d.notification is None
    assert d.new_state.last_status == "full"
    assert d.new_state.last_change_at == NOW.isoformat(timespec="seconds")
    assert d.new_state.consecutive_errors == 0


def test_unknown_to_available_urgent():
    d = decide(_state("unknown"), "available", NOW)
    assert d.notification is not None
    assert d.notification.kind == NotificationKind.AVAILABLE_DETECTED
    assert d.new_state.last_status == "available"


def test_full_to_full_silent_keeps_change_at():
    prev = _state("full", last_change="2026-04-27T07:05:12+09:00")
    d = decide(prev, "full", NOW)
    assert d.notification is None
    assert d.new_state.last_change_at == "2026-04-27T07:05:12+09:00"


def test_full_to_available_urgent():
    d = decide(_state("full"), "available", NOW)
    assert d.notification is not None
    assert d.notification.kind == NotificationKind.AVAILABLE_DETECTED


def test_available_to_available_silent():
    prev = _state("available", last_change="2026-04-27T07:05:12+09:00")
    d = decide(prev, "available", NOW)
    assert d.notification is None
    assert d.new_state.last_change_at == "2026-04-27T07:05:12+09:00"


def test_available_to_full_default_notify():
    d = decide(_state("available"), "full", NOW)
    assert d.notification is not None
    assert d.notification.kind == NotificationKind.BACK_TO_FULL


def test_error_to_available_urgent():
    d = decide(_state("error"), "available", NOW)
    assert d.notification is not None
    assert d.notification.kind == NotificationKind.AVAILABLE_DETECTED


def test_error_to_full_recovery_low():
    d = decide(_state("error"), "full", NOW)
    assert d.notification is not None
    assert d.notification.kind == NotificationKind.BACK_TO_FULL_FROM_ERROR


def test_error_first_two_silent_third_alerts():
    s = _state("full", consec=0)
    d1 = decide(s, None, NOW)
    assert d1.notification is None
    assert d1.new_state.consecutive_errors == 1
    assert d1.new_state.last_status == "full"

    d2 = decide(d1.new_state, None, NOW)
    assert d2.notification is None
    assert d2.new_state.consecutive_errors == 2

    d3 = decide(d2.new_state, None, NOW)
    assert d3.notification is not None
    assert d3.notification.kind == NotificationKind.ERROR_ALERT
    assert d3.new_state.last_status == "error"
    assert d3.new_state.consecutive_errors == 0


def test_error_state_subsequent_errors_silent():
    s = _state("error", consec=0)
    d = decide(s, None, NOW)
    assert d.notification is None
    assert d.new_state.last_status == "error"
    assert d.new_state.consecutive_errors == 1


def test_success_resets_consecutive_errors():
    prev = _state("full", consec=2)
    d = decide(prev, "full", NOW)
    assert d.new_state.consecutive_errors == 0


def test_load_state_missing_file_returns_initial(tmp_path):
    s = load_state(tmp_path / "nope.json", TARGET)
    assert s.target_date == TARGET
    assert s.last_status == "unknown"
    assert s.consecutive_errors == 0


def test_load_state_corrupted_returns_initial(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("not json", encoding="utf-8")
    s = load_state(p, TARGET)
    assert s.last_status == "unknown"


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    s = State(
        target_date=TARGET,
        last_status="full",
        last_check_at="2026-04-28T07:05:12+09:00",
        last_change_at="2026-04-28T07:05:12+09:00",
        consecutive_errors=1,
        last_health_check_at="2026-04-26T09:05:00+09:00",
    )
    save_state(p, s)
    loaded = load_state(p, TARGET)
    assert loaded == s


def test_should_send_health_check_after_8am_jst_first_time():
    morning = datetime(2026, 4, 30, 8, 5, 0, tzinfo=JST)
    s = _state("full", last_health=None)
    assert should_send_health_check(s, morning) is True


def test_should_not_send_health_check_before_8am_jst():
    early = datetime(2026, 4, 30, 7, 59, 0, tzinfo=JST)
    s = _state("full")
    assert should_send_health_check(s, early) is False


def test_should_not_send_if_already_sent_today():
    later = datetime(2026, 4, 30, 10, 5, 0, tzinfo=JST)
    s = _state("full", last_health="2026-04-30T08:05:00+09:00")
    assert should_send_health_check(s, later) is False


def test_should_send_next_day():
    next_day = datetime(2026, 5, 1, 8, 5, 0, tzinfo=JST)
    s = _state("full", last_health="2026-04-30T08:05:00+09:00")
    assert should_send_health_check(s, next_day) is True


def test_health_check_at_exactly_8am_jst():
    eight = datetime(2026, 4, 30, 8, 0, 0, tzinfo=JST)
    s = _state("full", last_health=None)
    assert should_send_health_check(s, eight) is True


def test_mark_health_check_sent_updates_only_health_field():
    s = _state("full")
    new = mark_health_check_sent(s, NOW)
    assert new.last_health_check_at == NOW.isoformat(timespec="seconds")
    assert new.last_status == "full"
