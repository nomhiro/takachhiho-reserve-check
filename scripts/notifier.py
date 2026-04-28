"""ntfy.sh への通知送信。

ntfy は JSON POST 形式 (https://docs.ntfy.sh/publish/#publish-as-json)
を使用する。ヘッダ方式 (Title 等) は HTTP ヘッダの latin-1 制約により
非ASCII値で UnicodeEncodeError を発生させるため避ける。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import requests

from scripts.log import log_event
from scripts.state import Notification, NotificationKind

NTFY_BASE = "https://ntfy.sh"
RESERVATION_URL = "https://eipro.jp/takachiho1/eventCalendars/index"
USER_AGENT = "takachiho-watch/0.1 (+https://github.com/nomhiro1204/takachhiho-reserve-check)"
TIMEOUT_SEC = 15


@dataclass
class NtfyPayload:
    """ntfy への JSON POST ボディ（topic フィールドは送信時に追加する）。"""

    title: str
    message: str
    priority: str
    tags: list[str]
    click: Optional[str] = None
    actions: Optional[list[dict]] = None


def _github_actions_url() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
        return f"https://github.com/{repo}/actions"
    return "https://github.com/<owner>/<repo>/actions"


def build_payload(notification: Notification) -> NtfyPayload:
    kind = notification.kind
    detected = notification.detected_at

    if kind == NotificationKind.AVAILABLE_DETECTED:
        return NtfyPayload(
            title="🚨 高千穂峡 5/8 空き検知！",
            message=f"検知時刻: {detected}\n急いで予約してください。",
            priority="urgent",
            tags=["rotating_light", "boat"],
            click=RESERVATION_URL,
            actions=[
                {
                    "action": "view",
                    "label": "予約サイトを開く",
                    "url": RESERVATION_URL,
                    "clear": True,
                }
            ],
        )

    if kind == NotificationKind.BACK_TO_FULL:
        return NtfyPayload(
            title="高千穂峡 5/8 満室に戻りました",
            message=f"先ほどの空きは埋まったようです。\n検知時刻: {detected}",
            priority="default",
            tags=["x"],
        )

    if kind == NotificationKind.BACK_TO_FULL_FROM_ERROR:
        return NtfyPayload(
            title="高千穂峡 5/8 監視復旧（満室）",
            message=f"監視エラーから復旧しました。現在は満室です。\n検知時刻: {detected}",
            priority="low",
            tags=["white_check_mark"],
        )

    if kind == NotificationKind.ERROR_ALERT:
        return NtfyPayload(
            title="⚠️ takachiho-watch エラー",
            message=(
                "3回連続で取得/パースに失敗しました。\n"
                "Actions ログを確認してください。\n"
                f"{_github_actions_url()}"
            ),
            priority="high",
            tags=["warning"],
        )

    if kind == NotificationKind.HEALTH_CHECK:
        status = notification.current_status or "unknown"
        return NtfyPayload(
            title="takachiho-watch 稼働中",
            message=(
                "今週も監視継続中です。\n"
                f"最終チェック: {detected}\n"
                f"現在の状態: {status}"
            ),
            priority="low",
            tags=["white_check_mark"],
        )

    raise ValueError(f"unknown notification kind: {kind}")


_PRIORITY_NUMERIC = {
    "min": 1,
    "low": 2,
    "default": 3,
    "high": 4,
    "urgent": 5,
}


def _to_request_body(topic: str, payload: NtfyPayload) -> dict:
    body: dict = {
        "topic": topic,
        "title": payload.title,
        "message": payload.message,
        "priority": _PRIORITY_NUMERIC[payload.priority],
        "tags": payload.tags,
    }
    if payload.click:
        body["click"] = payload.click
    if payload.actions:
        body["actions"] = payload.actions
    return body


def send(
    topic: str,
    notification: Notification,
    dry_run: bool = False,
    session: Optional[requests.Session] = None,
) -> bool:
    payload = build_payload(notification)

    if dry_run:
        log_event(
            "notify_dry_run",
            kind=str(notification.kind.value),
            title=payload.title,
            priority=payload.priority,
            tags=",".join(payload.tags),
            message_preview=payload.message[:200],
        )
        return True

    if not topic:
        log_event(
            "notify_skipped_no_topic",
            level="WARNING",
            kind=str(notification.kind.value),
        )
        return False

    body = _to_request_body(topic, payload)
    sess = session or requests
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json; charset=utf-8",
    }
    try:
        resp = sess.post(
            NTFY_BASE,
            json=body,
            headers=headers,
            timeout=TIMEOUT_SEC,
        )
        resp.raise_for_status()
        log_event(
            "notify_sent",
            kind=str(notification.kind.value),
            status_code=resp.status_code,
        )
        return True
    except requests.RequestException as e:
        log_event(
            "notify_failed",
            level="ERROR",
            kind=str(notification.kind.value),
            error=str(e),
        )
        return False
