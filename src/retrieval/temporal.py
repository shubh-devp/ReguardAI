import datetime
import logging

logger = logging.getLogger(__name__)

STATUS_FIELD = "status"

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
    return datetime.date.today()


def parse_date(value):
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
    if effective is None:
        return None
    reference = as_of or today()
    return (reference - effective).days


def latest_by_regulation(passages):
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
    from src.retrieval.provenance import load_curated_passages

    reference = as_of or today()
    if passages is None:
        passages = load_curated_passages()

    effective = parse_date(block.get("effective_date"))
    status = block.get("status")
    warnings = []

    if effective is None:
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
    if not currency:
        return True
    return not (currency.get("superseded") or currency.get("status_inactive"))
