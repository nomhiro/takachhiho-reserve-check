"""JSON Lines 構造化ログ。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def log_event(event: str, level: str = "INFO", **fields: Any) -> None:
    record = {"ts": _now_iso(), "level": level, "event": event}
    record.update(fields)
    sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
    sys.stdout.flush()
