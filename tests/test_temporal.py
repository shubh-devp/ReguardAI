"""Temporal and version awareness for retrieved regulatory evidence.

The corpus records an effective date and a lifecycle status per passage. These
tests use small hand-written passages rather than corpus rows, because the real
corpus is almost entirely dated "unknown" and a supersession case cannot be
demonstrated from it. The helpers are pure functions, so the input is the whole
test.
"""

import datetime

from src.retrieval import temporal

REGULATION = "Reserve Bank of India (Digital Lending) Directions, 2025"


def passage(passage_id, effective_date, regulation=REGULATION, status="active", section="Para 1"):
    return {
        "passage_id": passage_id,
        "effective_date": effective_date,
        "regulation": regulation,
        "status": status,
        "section": section,
    }


def test_dates_are_parsed_in_the_formats_the_corpus_uses():
    assert temporal.parse_date("May 8, 2025") == datetime.date(2025, 5, 8)
    assert temporal.parse_date("January 1, 2024") == datetime.date(2024, 1, 1)
    assert temporal.parse_date("2024-01-01") == datetime.date(2024, 1, 1)


def test_an_empty_or_unknown_date_is_not_an_error():
    """Most of the corpus has no date recorded, so this is the common path."""
    assert temporal.parse_date(None) is None
    assert temporal.parse_date("") is None
    assert temporal.parse_date("not a date") is None


def test_age_is_measured_from_the_as_of_date():
    effective = datetime.date(2025, 1, 1)
    assert temporal.age_in_days(effective, datetime.date(2025, 1, 31)) == 30
    assert temporal.age_in_days(None, datetime.date(2025, 1, 31)) is None


def test_a_passage_with_no_date_is_reported_as_unknown_not_stale():
    block = {"passage_id": "X-1", "effective_date": None, "status": "active", "regulation": REGULATION}
    result = temporal.assess(block, passages=[], as_of=datetime.date(2026, 1, 1))

    assert result["effective_date_iso"] is None
    assert result["age_days"] is None
    assert result["is_current"] is False
    assert result["warnings"] == ["effective date not recorded in the corpus"]
    # Unknown is a warning, not a reason to block remediation.
    assert temporal.reliance_safe(result) is True


def test_a_newer_passage_of_the_same_regulation_is_flagged_as_superseding():
    older = passage("RBI-DL-0010", "January 1, 2024")
    newer = passage("RBI-DL-0020", "May 8, 2025", section="Para 7")

    result = temporal.assess(older, passages=[older, newer], as_of=datetime.date(2026, 1, 1))

    assert result["superseded"] is True
    assert result["newer_passage"]["passage_id"] == "RBI-DL-0020"
    assert temporal.reliance_safe(result) is False


def test_the_newest_passage_is_not_flagged_as_superseded_by_itself():
    older = passage("RBI-DL-0010", "January 1, 2024")
    newer = passage("RBI-DL-0020", "May 8, 2025")

    result = temporal.assess(newer, passages=[older, newer], as_of=datetime.date(2026, 1, 1))

    assert result["superseded"] is False
    assert temporal.reliance_safe(result) is True


def test_a_different_regulation_never_supersedes():
    """Supersession is scoped to one regulation, so an unrelated newer document is ignored."""
    block = passage("RBI-DL-0010", "January 1, 2024")
    other = passage("RBI-PC-0001", "May 8, 2025", regulation="Reserve Bank of India (Penal Charges) Directions, 2023")

    result = temporal.assess(block, passages=[block, other], as_of=datetime.date(2026, 1, 1))

    assert result["superseded"] is False


def test_a_withdrawn_status_blocks_reliance():
    block = passage("RBI-DL-0030", "May 8, 2025", status="withdrawn")
    result = temporal.assess(block, passages=[block], as_of=datetime.date(2026, 1, 1))

    assert result["status_inactive"] is True
    assert any("withdrawn" in warning for warning in result["warnings"])
    assert temporal.reliance_safe(result) is False


def test_an_undated_passage_is_excluded_from_the_newest_lookup():
    """"Newest" is meaningless without dates, so undated rows must not win."""
    undated = passage("RBI-DL-0001", None)
    dated = passage("RBI-DL-0002", "January 1, 2024")

    latest = temporal.latest_by_regulation([undated, dated])

    assert latest[REGULATION][1]["passage_id"] == "RBI-DL-0002"


def test_the_real_corpus_is_assessed_without_raising(curated_passages):
    """Every curated passage must survive the currency check."""
    for row in curated_passages:
        result = temporal.assess(row, passages=curated_passages, as_of=datetime.date(2026, 9, 16))
        assert isinstance(result["warnings"], list)
        assert isinstance(result["superseded"], bool)
        assert isinstance(temporal.reliance_safe(result), bool)
