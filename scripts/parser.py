"""空き状況 JSON レスポンスから対象日の状態を抽出する。"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

Status = Literal["available", "full"]


class ParserError(Exception):
    """パース失敗（スキーマ不正、空レスポンス、想定外構造）。"""


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
    }


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
