import requests

from scripts.notifier import NTFY_BASE, build_payload, send
from scripts.state import Notification, NotificationKind

DETECTED = "2026-04-28T07:05:12+09:00"
TOPIC = "test-topic-do-not-use-in-prod"


def test_available_payload_urgent():
    n = Notification(kind=NotificationKind.AVAILABLE_DETECTED, detected_at=DETECTED)
    p = build_payload(n)
    assert p.priority == "urgent"
    assert "🚨" in p.title
    assert "5/8" in p.title
    assert p.tags == ["rotating_light", "boat"]
    assert p.click == "https://eipro.jp/takachiho1/eventCalendars/index"
    assert DETECTED in p.message
    assert p.actions and p.actions[0]["action"] == "view"


def test_back_to_full_payload_default():
    n = Notification(kind=NotificationKind.BACK_TO_FULL, detected_at=DETECTED)
    p = build_payload(n)
    assert p.priority == "default"
    assert p.tags == ["x"]
    assert "満室" in p.title


def test_recovery_from_error_payload_low():
    n = Notification(
        kind=NotificationKind.BACK_TO_FULL_FROM_ERROR, detected_at=DETECTED
    )
    p = build_payload(n)
    assert p.priority == "low"
    assert "復旧" in p.title


def test_error_alert_payload_high():
    n = Notification(kind=NotificationKind.ERROR_ALERT, detected_at=DETECTED)
    p = build_payload(n)
    assert p.priority == "high"
    assert "⚠️" in p.title
    assert p.tags == ["warning"]


def test_health_check_payload_low_includes_status():
    n = Notification(
        kind=NotificationKind.HEALTH_CHECK,
        detected_at=DETECTED,
        current_status="full",
    )
    p = build_payload(n)
    assert p.priority == "low"
    assert "稼働中" in p.title
    assert "full" in p.message


def test_dry_run_does_not_call_http(requests_mock):
    requests_mock.post(NTFY_BASE)
    n = Notification(kind=NotificationKind.AVAILABLE_DETECTED, detected_at=DETECTED)
    send(TOPIC, n, dry_run=True)
    assert requests_mock.call_count == 0


def test_send_posts_json_with_correct_body(requests_mock):
    requests_mock.post(NTFY_BASE, json={"id": "abc"})
    n = Notification(kind=NotificationKind.AVAILABLE_DETECTED, detected_at=DETECTED)
    ok = send(TOPIC, n, dry_run=False)
    assert ok is True

    req = requests_mock.last_request
    body = req.json()
    assert body["topic"] == TOPIC
    assert body["priority"] == 5  # urgent → 5
    assert body["tags"] == ["rotating_light", "boat"]
    assert body["title"].startswith("🚨")
    assert DETECTED in body["message"]
    assert body["click"] == "https://eipro.jp/takachiho1/eventCalendars/index"
    assert req.headers["User-Agent"].startswith("takachiho-watch/")
    assert req.headers["Content-Type"].startswith("application/json")


def test_send_returns_false_on_http_error(requests_mock):
    requests_mock.post(NTFY_BASE, status_code=500)
    n = Notification(kind=NotificationKind.AVAILABLE_DETECTED, detected_at=DETECTED)
    ok = send(TOPIC, n, dry_run=False)
    assert ok is False


def test_send_swallows_connection_errors(requests_mock):
    requests_mock.post(NTFY_BASE, exc=requests.exceptions.ConnectionError)
    n = Notification(kind=NotificationKind.AVAILABLE_DETECTED, detected_at=DETECTED)
    ok = send(TOPIC, n, dry_run=False)
    assert ok is False


def test_send_skipped_when_topic_empty(requests_mock):
    requests_mock.post(NTFY_BASE)
    n = Notification(kind=NotificationKind.AVAILABLE_DETECTED, detected_at=DETECTED)
    ok = send("", n, dry_run=False)
    assert ok is False
    assert requests_mock.call_count == 0
