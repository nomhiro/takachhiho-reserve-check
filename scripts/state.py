"""状態遷移ロジックと state.json 永続化。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Literal, Optional

JST = timezone(timedelta(hours=9))

ERROR_THRESHOLD = 3

Status = Literal["unknown", "full", "available", "error"]


class NotificationKind(str, Enum):
    AVAILABLE_DETECTED = "available_detected"
    BACK_TO_FULL = "back_to_full"
    BACK_TO_FULL_FROM_ERROR = "back_to_full_from_error"
    ERROR_ALERT = "error_alert"
    HEALTH_CHECK = "health_check"


@dataclass
class Notification:
    kind: NotificationKind
    detected_at: str
    current_status: Optional[str] = None


@dataclass
class State:
    target_date: str
    last_status: Status = "unknown"
    last_check_at: Optional[str] = None
    last_change_at: Optional[str] = None
    consecutive_errors: int = 0
    last_health_check_at: Optional[str] = None


@dataclass
class Decision:
    new_state: State
    notification: Optional[Notification] = None


def to_iso(dt: datetime) -> str:
    return dt.astimezone(JST).isoformat(timespec="seconds")


_iso = to_iso


def load_state(path: Path, target_date: str) -> State:
    if not path.exists():
        return State(target_date=target_date)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return State(target_date=target_date)
    if not isinstance(raw, dict):
        return State(target_date=target_date)
    return State(
        target_date=raw.get("target_date", target_date),
        last_status=raw.get("last_status", "unknown"),
        last_check_at=raw.get("last_check_at"),
        last_change_at=raw.get("last_change_at"),
        consecutive_errors=int(raw.get("consecutive_errors", 0) or 0),
        last_health_check_at=raw.get("last_health_check_at"),
    )


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def decide(
    prev: State,
    observed: Optional[Literal["available", "full"]],
    now: datetime,
) -> Decision:
    now_iso = _iso(now)

    if observed is None:
        return _decide_on_error(prev, now_iso)

    return _decide_on_status(prev, observed, now_iso)


def _decide_on_error(prev: State, now_iso: str) -> Decision:
    new_consec = prev.consecutive_errors + 1

    if new_consec >= ERROR_THRESHOLD and prev.last_status != "error":
        new = State(
            target_date=prev.target_date,
            last_status="error",
            last_check_at=now_iso,
            last_change_at=now_iso,
            consecutive_errors=0,
            last_health_check_at=prev.last_health_check_at,
        )
        return Decision(
            new_state=new,
            notification=Notification(
                kind=NotificationKind.ERROR_ALERT,
                detected_at=now_iso,
            ),
        )

    new = State(
        target_date=prev.target_date,
        last_status=prev.last_status,
        last_check_at=now_iso,
        last_change_at=prev.last_change_at,
        consecutive_errors=new_consec,
        last_health_check_at=prev.last_health_check_at,
    )
    return Decision(new_state=new, notification=None)


def _decide_on_status(
    prev: State, new_status: Literal["available", "full"], now_iso: str
) -> Decision:
    notification: Optional[Notification] = None
    change_at = prev.last_change_at

    if prev.last_status != new_status:
        change_at = now_iso
        if prev.last_status in ("unknown", "full") and new_status == "available":
            notification = Notification(
                kind=NotificationKind.AVAILABLE_DETECTED,
                detected_at=now_iso,
                current_status=new_status,
            )
        elif prev.last_status == "available" and new_status == "full":
            notification = Notification(
                kind=NotificationKind.BACK_TO_FULL,
                detected_at=now_iso,
                current_status=new_status,
            )
        elif prev.last_status == "error" and new_status == "available":
            notification = Notification(
                kind=NotificationKind.AVAILABLE_DETECTED,
                detected_at=now_iso,
                current_status=new_status,
            )
        elif prev.last_status == "error" and new_status == "full":
            notification = Notification(
                kind=NotificationKind.BACK_TO_FULL_FROM_ERROR,
                detected_at=now_iso,
                current_status=new_status,
            )

    new = State(
        target_date=prev.target_date,
        last_status=new_status,
        last_check_at=now_iso,
        last_change_at=change_at,
        consecutive_errors=0,
        last_health_check_at=prev.last_health_check_at,
    )
    return Decision(new_state=new, notification=notification)


HEALTH_CHECK_HOUR_JST = 8


def should_send_health_check(prev: State, now: datetime) -> bool:
    """毎日 08:00 JST 以降、まだ今日送っていない場合 True。"""
    now_jst = now.astimezone(JST)
    if now_jst.hour < HEALTH_CHECK_HOUR_JST:
        return False
    if prev.last_health_check_at:
        try:
            last = datetime.fromisoformat(prev.last_health_check_at)
        except ValueError:
            return True
        if last.astimezone(JST).date() == now_jst.date():
            return False
    return True


def mark_health_check_sent(state: State, now: datetime) -> State:
    return State(
        target_date=state.target_date,
        last_status=state.last_status,
        last_check_at=state.last_check_at,
        last_change_at=state.last_change_at,
        consecutive_errors=state.consecutive_errors,
        last_health_check_at=_iso(now),
    )
