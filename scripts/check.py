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

from scripts import fetcher, notifier, parser, summary  # noqa: E402
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
    target_entry = None
    slots: list[parser.Slot] = []
    try:
        payload = fetcher.fetch(target_date)
        results_count = len(payload.get("results", [])) if isinstance(payload, dict) else 0
        log_event("fetch_ok", results_count=results_count)
        target_entry = parser.find_target_entry(payload, target_date)
        log_event(
            "target_entry",
            **parser.summarize_target_entry(target_entry),
        )

        # 時間スロット詳細を取得（target_entry に session_cd / service_cd があれば）
        if target_entry and target_entry.get("session_cd") and target_entry.get("service_cd"):
            try:
                slot_payload = fetcher.fetch_slot_detail(
                    service_cd=target_entry["service_cd"],
                    session_cd=target_entry["session_cd"],
                    target_date=target_date,
                )
                slots = parser.parse_slots(slot_payload)
                log_event(
                    "slots_parsed",
                    total=len(slots),
                    ordable=sum(1 for s in slots if s.ordable),
                )
                for s in slots:
                    log_event(
                        "slot",
                        start=s.start_time,
                        end=s.end_time,
                        ordable=s.ordable,
                        icon=s.icon,
                    )
            except (fetcher.FetchError, parser.ParserError) as e:
                # 時間詳細取得が失敗しても、日サマリで判定継続
                log_event(
                    "slot_detail_skipped",
                    level="WARNING",
                    error_type=type(e).__name__,
                    error=str(e),
                )
                slots = []

        # 状態判定: 時間スロットが取れていればそれを最優先、無ければ日サマリ
        if slots:
            observed = parser.status_from_slots(slots)
            log_event("parse_ok", status=observed, source="hourly_slots")
        else:
            observed = parser.parse(payload, target_date)
            log_event("parse_ok", status=observed, source="day_summary")
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
        # urgent 通知には空きスロット詳細を載せる
        if decision.notification.kind == NotificationKind.AVAILABLE_DETECTED and slots:
            open_slots = [(s.start_time, s.end_time) for s in slots if s.ordable]
            decision.notification.open_slots = open_slots
            decision.notification.total_slots = len(slots)
        log_event(
            "notification_dispatch",
            kind=str(decision.notification.kind.value),
            prev_status=state.last_status,
            new_status=new_state.last_status,
            open_slots_count=len(decision.notification.open_slots or []),
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

    # GitHub Actions の run page に Markdown サマリを出す
    md = summary.build_markdown(
        target_date=target_date,
        target_entry=target_entry,
        slots=slots,
        overall_status=new_state.last_status,
        last_change_at=new_state.last_change_at,
    )
    summary.write_step_summary(md)

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
