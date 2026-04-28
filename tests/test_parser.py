from datetime import date

import pytest

from scripts.parser import ParserError, find_target_entry, parse, summarize_target_entry
from tests.conftest import load_fixture

TARGET = date(2026, 5, 8)


def test_available_fixture_returns_available():
    payload = load_fixture("available.json")
    assert parse(payload, TARGET) == "available"


def test_full_fixture_returns_full():
    payload = load_fixture("full.json")
    assert parse(payload, TARGET) == "full"


def test_missing_target_date_treated_as_full():
    payload = load_fixture("missing_target.json")
    assert parse(payload, TARGET) == "full"


def test_empty_payload_raises():
    with pytest.raises(ParserError):
        parse({}, TARGET)


def test_results_not_list_raises():
    with pytest.raises(ParserError):
        parse({"results": "oops"}, TARGET)


def test_error_response_raises():
    payload = load_fixture("error.json")
    with pytest.raises(ParserError):
        parse(payload, TARGET)


def test_non_dict_payload_raises():
    with pytest.raises(ParserError):
        parse("not a dict", TARGET)  # type: ignore[arg-type]


def test_target_entry_without_ordable_raises():
    payload = {
        "results": [
            {"service_date": "2026/05/08"}
        ]
    }
    with pytest.raises(ParserError):
        parse(payload, TARGET)


def test_dash_format_service_date_also_supported():
    payload = {
        "results": [
            {"service_date": "2026-05-08", "ordable": True}
        ]
    }
    assert parse(payload, TARGET) == "available"


def test_find_target_entry_returns_dict_when_present():
    payload = load_fixture("full.json")
    entry = find_target_entry(payload, TARGET)
    assert entry is not None
    assert entry["service_date"] == "2026/05/08"
    assert entry["ordable"] is False


def test_find_target_entry_returns_none_when_absent():
    payload = load_fixture("missing_target.json")
    assert find_target_entry(payload, TARGET) is None


def test_find_target_entry_safe_on_bad_payload():
    assert find_target_entry({}, TARGET) is None
    assert find_target_entry(None, TARGET) is None
    assert find_target_entry({"results": "x"}, TARGET) is None


def test_summarize_target_entry_strips_title_html():
    payload = load_fixture("available.json")
    entry = find_target_entry(payload, TARGET)
    summary = summarize_target_entry(entry)
    assert summary["found"] is True
    assert summary["ordable"] is True
    assert summary["service_date"] == "2026/05/08"
    assert "title" not in summary  # title (HTML) は要約から除外


def test_summarize_target_entry_none():
    assert summarize_target_entry(None) == {"found": False}
