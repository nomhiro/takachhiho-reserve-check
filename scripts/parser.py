"""空き状況 JSON レスポンスから対象日の状態を抽出する。

- 月ビュー API: 各日のサマリ（ordable=true/false の1値）
- 時間スロット詳細 API: その日の30分刻みスロット (HTML in JSON)

時間ごとの空き把握には詳細 API のパースが必要。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Optional

from bs4 import BeautifulSoup

Status = Literal["available", "full"]


class ParserError(Exception):
    """パース失敗（スキーマ不正、空レスポンス、想定外構造）。"""


@dataclass
class Slot:
    start_time: str  # "08:30"
    end_time: str    # "09:00"
    ordable: bool
    icon: str        # "fa-times" / "fa-circle" 等
    raw_class: str   # service_unit のクラス（calendar_color_no_orderable 等）


def _normalize_service_date(service_date: str) -> str:
    return service_date.replace("/", "-").strip()


def _validate_payload(payload: Any) -> list:
    if not isinstance(payload, dict):
        raise ParserError(f"payload is not a dict: {type(payload).__name__}")
    if "results" not in payload:
        raise ParserError("'results' key missing in payload")
    results = payload["results"]
    if not isinstance(results, list):
        raise ParserError(f"'results' is not a list: {type(results).__name__}")
    return results


def find_target_entry(payload: Any, target_date: date) -> Optional[dict]:
    """target_date に対応する results エントリを返す。なければ None。

    ログ用途のヘルパー。スキーマ検証は行わない（行うと parse() と二重に raise する）。
    """
    if not isinstance(payload, dict):
        return None
    results = payload.get("results")
    if not isinstance(results, list):
        return None
    target_iso = target_date.isoformat()
    for entry in results:
        if not isinstance(entry, dict):
            continue
        sd = entry.get("service_date")
        if isinstance(sd, str) and _normalize_service_date(sd) == target_iso:
            return entry
    return None


def summarize_target_entry(entry: Optional[dict]) -> dict:
    """ログに残す用の要約。title (HTML) は除外。"""
    if entry is None:
        return {"found": False}
    return {
        "found": True,
        "service_date": entry.get("service_date"),
        "ordable": entry.get("ordable"),
        "color": entry.get("color"),
        "min_price": entry.get("min_price"),
        "max_price": entry.get("max_price"),
        "cancel_wait_possible": entry.get("cancel_wait_possible"),
        "start": entry.get("start"),
        "end": entry.get("end"),
        "session_cd": entry.get("session_cd"),
        "service_cd": entry.get("service_cd"),
    }


def parse_slots(payload: Any) -> list[Slot]:
    """時間スロット詳細 API のレスポンスから Slot 一覧を抽出する。

    payload は order_detail_datetime_selector が返す JSON。
    payload["data"] が HTML 文字列。各 service_unit が1スロット。
    """
    if not isinstance(payload, dict):
        raise ParserError(f"slot payload not a dict: {type(payload).__name__}")
    html = payload.get("data")
    if not isinstance(html, str):
        # サーバ側でデータなし時に [] を返すケースがある
        if isinstance(html, list):
            return []
        raise ParserError(f"'data' is not str/list: {type(html).__name__}")
    if not html.strip():
        return []

    soup = BeautifulSoup(html, "html.parser")
    slots: list[Slot] = []
    for unit in soup.select(".service_unit"):
        classes = unit.get("class") or []
        raw_class = " ".join(classes)

        times = unit.select(".term_time")
        if len(times) < 2:
            continue
        start = times[0].get_text(strip=True)
        end = times[1].get_text(strip=True)
        if not re.match(r"^\d{1,2}:\d{2}$", start) or not re.match(r"^\d{1,2}:\d{2}$", end):
            continue

        icon_el = unit.select_one(".service_icon i, i.fa-icon")
        icon_classes = icon_el.get("class") if icon_el is not None else []
        icon = " ".join(c for c in (icon_classes or []) if c.startswith("fa-"))

        no_orderable = "calendar_color_no_orderable" in classes
        is_full_icon = icon_el is not None and "fa-times" in (icon_classes or [])
        ordable = not (no_orderable or is_full_icon)

        slots.append(
            Slot(
                start_time=start,
                end_time=end,
                ordable=ordable,
                icon=icon,
                raw_class=raw_class,
            )
        )
    return slots


def status_from_slots(slots: list[Slot]) -> Status:
    """時間スロットから日全体の状態を導出。1つでも ordable なら available。"""
    return "available" if any(s.ordable for s in slots) else "full"


def parse(payload: Any, target_date: date) -> Status:
    results = _validate_payload(payload)
    target_iso = target_date.isoformat()

    for entry in results:
        if not isinstance(entry, dict):
            raise ParserError("entry in 'results' is not a dict")

        service_date = entry.get("service_date")
        if not isinstance(service_date, str):
            continue

        if _normalize_service_date(service_date) != target_iso:
            continue

        ordable = entry.get("ordable")
        if not isinstance(ordable, bool):
            raise ParserError(
                f"'ordable' missing or non-bool for {service_date}: {ordable!r}"
            )
        return "available" if ordable else "full"

    return "full"
