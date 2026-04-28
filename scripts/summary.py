"""GitHub Actions の Step Summary に書き出すマークダウンレポート。"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Optional

from scripts.parser import Slot


def _icon(ordable: Optional[bool]) -> str:
    if ordable is True:
        return "⭕"
    if ordable is False:
        return "❌"
    return "❓"


def build_markdown(
    target_date: date,
    target_entry: Optional[dict],
    slots: list[Slot],
    overall_status: str,
    last_change_at: Optional[str],
) -> str:
    """run page に表示するマークダウン要約を生成する。"""
    lines = []
    lines.append(f"## takachiho-watch — {target_date.isoformat()} のチェック結果\n")

    headline_icon = _icon(target_entry.get("ordable") if target_entry else None)
    lines.append(f"### 総合判定: {headline_icon} **{overall_status}**\n")
    if last_change_at:
        lines.append(f"- 最終変化時刻: `{last_change_at}`\n")

    if target_entry:
        lines.append("\n### 日サマリ（月ビュー API）\n")
        lines.append("| 項目 | 値 |")
        lines.append("|---|---|")
        lines.append(f"| service_date | `{target_entry.get('service_date')}` |")
        lines.append(f"| ordable | `{target_entry.get('ordable')}` |")
        lines.append(f"| color | `{target_entry.get('color')}` |")
        lines.append(f"| min_price / max_price | `{target_entry.get('min_price')}` / `{target_entry.get('max_price')}` |")
        lines.append(f"| cancel_wait_possible | `{target_entry.get('cancel_wait_possible')}` |")

    lines.append("\n### 時間スロット詳細（30分刻み）\n")
    if not slots:
        lines.append("_スロット情報が取得できませんでした（API 仕様変更の可能性）_\n")
    else:
        ordable_count = sum(1 for s in slots if s.ordable)
        lines.append(f"**{ordable_count} / {len(slots)} スロット予約可能**\n")
        lines.append("| 時間 | 状態 | アイコン |")
        lines.append("|---|---|---|")
        for s in slots:
            lines.append(
                f"| {s.start_time}-{s.end_time} | {_icon(s.ordable)} | `{s.icon or '-'}` |"
            )

    return "\n".join(lines) + "\n"


def write_step_summary(markdown: str) -> bool:
    """$GITHUB_STEP_SUMMARY が指すファイルに追記する。

    GitHub Actions 上でなければ何もしない。
    """
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return False
    p = Path(path)
    with p.open("a", encoding="utf-8") as f:
        f.write(markdown)
    return True
