"""空き状況 JSON レスポンスから対象日の状態を抽出する。"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

Status = Literal["available", "full"]


class ParserError(Exception):
    """パース失敗（スキーマ不正、空レスポンス、想定外構造）。"""


def _normalize_service_date(service_date: str) -> str:
    return service_date.replace("/", "-").strip()


def parse(payload: Any, target_date: date) -> Status:
    if not isinstance(payload, dict):
        raise ParserError(f"payload is not a dict: {type(payload).__name__}")

    if "results" not in payload:
        raise ParserError("'results' key missing in payload")

    results = payload["results"]
    if not isinstance(results, list):
        raise ParserError(f"'results' is not a list: {type(results).__name__}")

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
