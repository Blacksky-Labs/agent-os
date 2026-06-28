"""Pure unit tests for the deterministic extractors — no LLM, no I/O."""

from cells.ingestion.extractors import (
    extract_all,
    extract_dates,
    extract_money,
    extract_proper_nouns,
)


def test_email_phone_url():
    text = "Reach me at mario@blacksky.com or 415-555-0142, see https://blacksky.org"
    out = extract_all(text)
    assert "mario@blacksky.com" in out["emails"]
    assert any("415" in p for p in out["phones"])
    assert any("blacksky.org" in u for u in out["urls"])


def test_money_ranges():
    assert extract_money("budget is $25k") == ["$25k"]
    # a hyphen range stays a single match
    assert extract_money("around $20-25k please")[0].startswith("$20")


def test_proper_nouns_camelcase():
    ents = extract_proper_nouns("today my goals are KNowGov and AgentOS with Jordan Tran")
    assert "KNowGov" in ents
    assert "AgentOS" in ents
    assert "Jordan Tran" in ents
    # common lowercase / stopwords excluded
    assert "today" not in [e.lower() for e in ents]


def test_dates_and_quarters():
    out = extract_dates("ship by Q3, call Tuesday at 2pm, deadline 2026-09-01")
    assert "Q3" in out
    assert any(d.lower().startswith("tue") for d in out)
    assert "2026-09-01" in out


def test_empty_and_none_safe():
    assert extract_all("") == {}
    assert extract_all(None) == {}
