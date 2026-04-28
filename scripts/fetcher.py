"""高千穂峡予約サイトの空き状況 API 取得。"""
from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Optional

import requests

from scripts.log import log_event

ENDPOINT = "https://eipro.jp/takachiho1/eventCalendars/search"
SLOT_DETAIL_ENDPOINT = "https://eipro.jp/takachiho1/apiServices/api/order_detail_datetime_selector"
USER_AGENT = "takachiho-watch/0.1 (+https://github.com/nomhiro1204/takachhiho-reserve-check)"
TIMEOUT_SEC = 20
MAX_RETRIES = 3
BACKOFF_BASE_SEC = 1.0
WINDOW_DAYS = 7


class FetchError(Exception):
    """取得失敗（リトライ後も失敗、4xx、JSON 不正）。"""


def fetch(
    target_date: date,
    session: Optional[requests.Session] = None,
    sleep=time.sleep,
) -> dict:
    sess = session or requests
    start = (target_date - timedelta(days=WINDOW_DAYS)).isoformat()
    end = (target_date + timedelta(days=WINDOW_DAYS)).isoformat()

    form = [
        ("data[conds][ServiceView][max_session_dateOver]", start),
        ("data[conds][ServiceView][min_session_dateUnder]", end),
        ("calendar_view_name", "month"),
        ("calendar_type", "month"),
    ]
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
    }

    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = sess.post(
                ENDPOINT,
                data=form,
                headers=headers,
                timeout=TIMEOUT_SEC,
            )
            log_event(
                "fetch_attempt",
                attempt=attempt,
                status_code=resp.status_code,
                bytes=len(resp.content),
            )
            if resp.status_code >= 500:
                last_exc = FetchError(f"server error {resp.status_code}")
            elif resp.status_code >= 400:
                raise FetchError(f"client error {resp.status_code}")
            else:
                try:
                    return resp.json()
                except ValueError as e:
                    raise FetchError(f"invalid JSON: {e}") from e
        except requests.RequestException as e:
            last_exc = e
            log_event("fetch_attempt_failed", level="WARNING", attempt=attempt, error=str(e))

        if attempt < MAX_RETRIES:
            sleep(BACKOFF_BASE_SEC * (2 ** (attempt - 1)))

    raise FetchError(f"all {MAX_RETRIES} attempts failed: {last_exc}") from last_exc


def fetch_slot_detail(
    service_cd: str,
    session_cd: str,
    target_date: date,
    session: Optional[requests.Session] = None,
    sleep=time.sleep,
) -> dict:
    """target_date の時間スロット詳細 (30分刻み) を取得する。

    返値の payload["data"] は HTML 文字列で、parser.parse_slots でパース可能。
    """
    sess = session or requests
    form = [
        ("data[service_cd]", service_cd),
        ("data[service_start_date]", target_date.isoformat()),
        ("data[session_cd]", session_cd),
        ("data[display_from]", "calendar"),
    ]
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
    }

    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = sess.post(
                SLOT_DETAIL_ENDPOINT,
                data=form,
                headers=headers,
                timeout=TIMEOUT_SEC,
            )
            log_event(
                "slot_detail_attempt",
                attempt=attempt,
                status_code=resp.status_code,
                bytes=len(resp.content),
            )
            if resp.status_code >= 500:
                last_exc = FetchError(f"slot detail server error {resp.status_code}")
            elif resp.status_code >= 400:
                raise FetchError(f"slot detail client error {resp.status_code}")
            else:
                try:
                    return resp.json()
                except ValueError as e:
                    raise FetchError(f"slot detail invalid JSON: {e}") from e
        except requests.RequestException as e:
            last_exc = e
            log_event(
                "slot_detail_attempt_failed",
                level="WARNING",
                attempt=attempt,
                error=str(e),
            )
        if attempt < MAX_RETRIES:
            sleep(BACKOFF_BASE_SEC * (2 ** (attempt - 1)))

    raise FetchError(f"slot_detail: all {MAX_RETRIES} attempts failed: {last_exc}") from last_exc
