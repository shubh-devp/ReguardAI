"""Temporal awareness for retrieved regulatory evidence.

RBI directions get amended and replaced. A finding that cites a paragraph which
has since been withdrawn is worse than one that cites nothing, because it still
looks authoritative to whoever reads the report. So every finding carries the
effective date and the lifecycle status of the passage it rests on, and the
pipeline says out loud when a newer passage of the same regulation exists.

The corpus is the source of truth here. Where a passage has no effective date
recorded, that is reported as "unknown" rather than guessed at, because a made-up
date is worse than a missing one.
"""

import datetime
import logging

logger = logging.getLogger(__name__)

STATUS_FIELD = "status"

# A passage whose status is not "active" has been replaced or pulled, so it
# should not be the basis of a live finding.
ACTIVE_STATUSES = frozenset({"active", "in-force", "in force", "current"})

DATE_FORMATS = (
    "%B %d, %Y",   # "May 8, 2025"
    "%b %d, %Y",   # "May 8, 2025"
    "%d %B %Y",    # "8 May 2025"
    "%d %b %Y",
    "%Y-%m-%d",    # ISO
    "%d/%m/%Y",
    "%m/%d/%Y",
)


def today():
    """The reference date for currency checks. Split out so tests can pin it."""
    return datetime.date.today()


def parse_date(value):
    """Parse a date the way the corpus writes it, or return None.

    The corpus stores dates as free text ("May 8, 2025") or leaves them empty, so
    a failure to parse is normal and is not an error.
    """
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, datetime.datetime):
        return value.date()

    text = str(value).strip()
    if not text:
        return None

    for date_format in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


def age_in_days(effective, as_of=None):
    """How old a passage is, or None when its date is unknown."""
    if effective is None:
        return None
    reference = as_of or today()
    return (reference - effective).days


def latest_by_regulation(passages):
    """The newest dated passage for each regulation family.

    Returns ``{regulation: (date, passage)}``. Regulations with no dated passage
    are left out, because "newest" is meaningless without dates.
    """
    latest = {}
    for passage in passages:
        regulation = passage.get("regulation")
        effective = parse_date(passage.get("effective_date"))
        if not regulation or effective is None:
            continue
        current = latest.get(regulation)
        if current is None or effective > current[0]:
            latest[regulation] = (effective, passage)
    return latest


def find_newer(block, passages):
    """The newest passage of the same regulation that is newer than this one.

    This is what lets the pipeline warn that a finding rests on an older version
    of a direction. It only fires when both dates are known, so it never invents
    supersession.
    """
    regulation = block.get("regulation")
    effective = parse_date(block.get("effective_date"))
    if not regulation or effective is None:
        return None

    candidates = [
        passage
        for passage in passages
        if passage.get("regulation") == regulation
        and passage.get("passage_id") != block.get("passage_id")
        and (parse_date(passage.get("effective_date")) or datetime.date.min) > effective
    ]
    if not candidates:
        return None

    newest = max(candidates, key=lambda passage: parse_date(passage.get("effective_date")))
    return {
        "passage_id": newest.get("passage_id"),
        "section": newest.get("section"),
        "effective_date": newest.get("effective_date"),
    }


def assess(block, passages=None, as_of=None):
    """Describe how current a piece of retrieved evidence is.

    ``block`` is a provenance block (see ``provenance.describe``). The result is
    flat, because it ends up in chunk metadata and in JSON responses.
    """
    from src.retrieval.provenance import load_curated_passages

    reference = as_of or today()
    if passages is None:
        passages = load_curated_passages()

    effective = parse_date(block.get("effective_date"))
    status = block.get("status")
    warnings = []

    if effective is None:
        # Most of the corpus has no date recorded, so this is the common case and
        # it is reported as unknown instead of being treated as stale.
        warnings.append("effective date not recorded in the corpus")
    if status is not None and str(status).strip().lower() not in ACTIVE_STATUSES:
        warnings.append(f"passage status is '{status}', not active")

    newer = find_newer(block, passages)
    if newer:
        warnings.append(
            "a newer passage of the same regulation exists: "
            f"{newer['passage_id']} ({newer['effective_date']})"
        )

    return {
        "as_of": reference.isoformat(),
        "effective_date": block.get("effective_date"),
        "effective_date_iso": effective.isoformat() if effective else None,
        "status": status,
        "age_days": age_in_days(effective, reference),
        "is_current": not warnings,
        "superseded": newer is not None,
        "status_inactive": status is not None and str(status).strip().lower() not in ACTIVE_STATUSES,
        "newer_passage": newer,
        "warnings": warnings,
    }


def reliance_safe(currency):
    """Whether a finding may be built on evidence in this state.

    A missing effective date is common in the corpus and is only a warning. A
    passage that has been replaced or pulled is different: relying on it would
    produce a confident finding grounded in a rule that no longer applies, so the
    pipeline fails closed on it instead.
    """
    if not currency:
        return True
    return not (currency.get("superseded") or currency.get("status_inactive"))









# """Temporal awareness and currency validation for retrieved regulatory evidence."""

# from pathlib import Path
# import datetime

# STATUS_FIELD = "status"
# ACTIVE_STATUSES = frozenset({"active", "in-force", "in force", "current"})

# DATE_FORMATS = (
#     "%B %d, %Y",
#     "%b %d, %Y",
#     "%d %B %Y",
#     "%d %b %Y",
#     "%Y-%m-%d",
#     "%d/%m/%Y",
#     "%m/%d/%Y",
# )


# def today():
#     """Return reference date for currency checks (swappable for testing)."""
#     return datetime.date.today()


# def parse_date(value):
#     """Parse flexible free-text date fields from the corpus safely."""
#     if value is None:
#         return None
#     if isinstance(value, datetime.date):
#         return value
#     if isinstance(value, datetime.datetime):
#         return value.date()

#     text = str(value).strip()
#     if not text:
#         return None

#     for date_format in DATE_FORMATS:
#         try:
#             return datetime.datetime.strptime(text, date_format).date()
#         except ValueError:
#             continue
#     return None


# def age_in_days(effective, as_of=None):
#     """Calculate the age of a regulatory passage in days."""
#     if effective is None:
#         return None
#     reference = as_of or today()
#     return (reference - effective).days


# def latest_by_regulation(passages):
#     """Identify the newest dated passage for each regulation family."""
#     latest = {}
#     for passage in passages:
#         regulation = passage.get("regulation")
#         effective = parse_date(passage.get("effective_date"))
#         if not regulation or effective is None:
#             continue
#         current = latest.get(regulation)
#         if current is None or effective > current[0]:
#             latest[regulation] = (effective, passage)
#     return latest


# def find_newer(block, passages):
#     """Check if a newer active version of the same regulation exists."""
#     regulation = block.get("regulation")
#     effective = parse_date(block.get("effective_date"))
#     if not regulation or effective is None:
#         return None

#     candidates = [
#         p for p in passages
#         if p.get("regulation") == regulation
#         and p.get("passage_id") != block.get("passage_id")
#         and (parse_date(p.get("effective_date")) or datetime.date.min) > effective
#     ]
#     if not candidates:
#         return None

#     newest = max(candidates, key=lambda p: parse_date(p.get("effective_date")))
#     return {
#         "passage_id": newest.get("passage_id"),
#         "section": newest.get("section"),
#         "effective_date": newest.get("effective_date"),
#     }


# def assess(block, passages=None, as_of=None):
#     """Assess the currency, lifecycle status, and supersession state of evidence."""
#     from src.retrieval.provenance import load_curated_passages

#     reference = as_of or today()
#     if passages is None:
#         passages = load_curated_passages()

#     effective = parse_date(block.get("effective_date"))
#     status = block.get("status")
#     warnings = []

#     if effective is None:
#         warnings.append("effective date not recorded in the corpus")
#     if status is not None and str(status).strip().lower() not in ACTIVE_STATUSES:
#         warnings.append(f"passage status is '{status}', not active")

#     newer = find_newer(block, passages)
#     if newer:
#         warnings.append(
#             f"a newer passage of the same regulation exists: {newer['passage_id']} ({newer['effective_date']})"
#         )

#     return {
#         "as_of": reference.isoformat(),
#         "effective_date": block.get("effective_date"),
#         "effective_date_iso": effective.isoformat() if effective else None,
#         "status": status,
#         "age_days": age_in_days(effective, reference),
#         "is_current": not warnings,
#         "superseded": newer is not None,
#         "status_inactive": status is not None and str(status).strip().lower() not in ACTIVE_STATUSES,
#         "newer_passage": newer,
#         "warnings": warnings,
#     }


# def reliance_safe(currency):
#     """Determine whether evidence can be safely relied upon or must fail closed."""
#     if not currency:
#         return True
#     return not (currency.get("superseded") or currency.get("status_inactive"))