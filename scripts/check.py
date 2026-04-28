#!/usr/bin/env python3
"""takachiho-watch エントリポイント。"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import fetcher, notifier, parser  # noqa: E402
from scripts.log import log_event  # noqa: E402
from scripts.state import (  # noqa: E402
    JST,
    Notification,
    NotificationKind,
    decide,
    load_state,
    mark_health_check_sent,
    save_state,
    should_send_health_check,
    to_iso,
)

DEFAULT_TARGET = date(2026, 5, 8)
DEFAULT_STATE_PATH = Path("state/state.json")


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="takachiho-watch reservation monitor")
    p.add_argument("--dry-run", action="store_true", help="通知送信を抑止")
    p.add_argument(
        "--target-date",
        default=DEFAULT_TARGET.isoformat(),
        help="監視対象日 (YYYY-MM-DD)",
    )
    p.add_argument(
        "--state-path",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help="state.json のパス",
    )
    return p.parse_args(argv)


def run(args: argparse.Namespace, now: datetime | None = None) -> int:
    now = now or datetime.now(JST)
    target_date = date.fromisoformat(args.target_date)

    if now.date() >= target_date:
        log_event("monitoring_period_ended", target=str(target_date), now=to_iso(now))
        return 0

    log_event("check_start", target=str(target_date), dry_run=args.dry_run)

    topic = os.environ.get("NTFY_TOPIC", "")

    state = load_state(args.state_path, target_date.isoformat())
    log_event(
        "state_loaded",
        last_status=state.last_status,
        consecutive_errors=state.consecutive_errors,
    )

    observed = None
    try:
        payload = fetcher.fetch(target_date)
        log_event("fetch_ok")
        observed = parser.parse(payload, target_date)
        log_event("parse_ok", status=observed)
    except (fetcher.FetchError, parser.ParserError) as e:
        log_event(
            "check_failed",
            level="ERROR",
            error_type=type(e).__name__,
            error=str(e),
        )
        observed = None

    decision = decide(state, observed, now)
    new_state = decision.new_state

    if decision.notification is not None:
        log_event(
            "notification_dispatch",
            kind=str(decision.notification.kind.value),
            prev_status=state.last_status,
            new_status=new_state.last_status,
        )
        notifier.send(topic, decision.notification, dry_run=args.dry_run)

    if should_send_health_check(new_state, now):
        log_event("health_check_dispatch")
        health = Notification(
            kind=NotificationKind.HEALTH_CHECK,
            detected_at=to_iso(now),
            current_status=new_state.last_status,
        )
        if notifier.send(topic, health, dry_run=args.dry_run) or args.dry_run:
            new_state = mark_health_check_sent(new_state, now)

    save_state(args.state_path, new_state)
    log_event(
        "check_end",
        new_status=new_state.last_status,
        consecutive_errors=new_state.consecutive_errors,
    )
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
