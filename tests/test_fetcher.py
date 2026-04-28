from datetime import date

import pytest
import requests

from scripts.fetcher import ENDPOINT, FetchError, fetch

TARGET = date(2026, 5, 8)


def test_fetch_success_returns_json(requests_mock):
    requests_mock.post(ENDPOINT, json={"results": [], "errors": []})
    payload = fetch(TARGET)
    assert payload == {"results": [], "errors": []}

    req = requests_mock.last_request
    body = req.text
    assert "data%5Bconds%5D%5BServiceView%5D%5Bmax_session_dateOver%5D=2026-05-01" in body
    assert "data%5Bconds%5D%5BServiceView%5D%5Bmin_session_dateUnder%5D=2026-05-15" in body
    assert "calendar_view_name=month" in body
    assert req.headers["X-Requested-With"] == "XMLHttpRequest"
    assert req.headers["User-Agent"].startswith("takachiho-watch/")


def test_fetch_4xx_raises_no_retry(requests_mock):
    requests_mock.post(ENDPOINT, status_code=404)
    with pytest.raises(FetchError):
        fetch(TARGET, sleep=lambda _: None)
    assert requests_mock.call_count == 1


def test_fetch_5xx_retries_then_raises(requests_mock):
    requests_mock.post(ENDPOINT, status_code=503)
    sleeps = []
    with pytest.raises(FetchError):
        fetch(TARGET, sleep=sleeps.append)
    assert requests_mock.call_count == 3
    assert sleeps == [1.0, 2.0]


def test_fetch_5xx_then_success(requests_mock):
    requests_mock.post(
        ENDPOINT,
        [
            {"status_code": 503, "text": "fail"},
            {"json": {"results": [{"service_date": "2026/05/08", "ordable": True}]}},
        ],
    )
    payload = fetch(TARGET, sleep=lambda _: None)
    assert payload["results"][0]["ordable"] is True


def test_fetch_invalid_json_raises(requests_mock):
    requests_mock.post(ENDPOINT, status_code=200, text="<html>not json</html>")
    with pytest.raises(FetchError):
        fetch(TARGET, sleep=lambda _: None)


def test_fetch_timeout_retries(requests_mock):
    requests_mock.post(
        ENDPOINT,
        [
            {"exc": requests.exceptions.Timeout},
            {"exc": requests.exceptions.Timeout},
            {"json": {"results": []}},
        ],
    )
    payload = fetch(TARGET, sleep=lambda _: None)
    assert payload == {"results": []}
