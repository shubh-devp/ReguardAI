import json
import logging

from src.retrieval import provenance

logger = logging.getLogger(__name__)

BENCHMARK_PATH = "data/benchmarks/policy_loophole_eval_benchmark.json"

TOPIC_SEVERITY_RULE = {
    "penal charges": "High",              
    "Direct disbursal": "High",          
    "Data sharing/consent": "High",       
    "APR/KFS disclosure": "Medium",       
    "Cooling-off period": "Medium",     
    "LSP due diligence/governance": "Medium",
    "DLA/LSP disclosure": "Medium",
    "Credit line enhancement": "Medium",
    "FLDG/DLG": "Medium",
    "Grievance redressal": "Low",
}

DEFAULT_SEVERITY = "Medium"


def load_benchmark(path=BENCHMARK_PATH):
    """Return the raw benchmark dict."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_gold_evidence(clauses):
    resolved = []
    unresolved = []

    for clause in clauses:
        gold_pages = []
        for passage_id in clause.get("mapped_passage_ids") or []:
            for passage in _passages_by_id().get(passage_id, []):
                gold_pages.append(
                    {
                        "passage_id": passage_id,
                        "document": passage.get("source_document"),
                        "page": passage.get("page"),
                        "section": passage.get("section"),
                        "regulation": passage.get("regulation"),
                    }
                )
            if passage_id not in _passages_by_id():
                unresolved.append(passage_id)

        if not gold_pages:
            logger.warning("No gold evidence resolved for clause %s", clause.get("clause_id"))

        record = dict(clause)
        record["gold_pages"] = gold_pages
        resolved.append(record)

    if unresolved:
        logger.warning("%d passage ids did not resolve to a curated passage", len(unresolved))

    return resolved


def add_derived_severity(records):
    for record in records:
        record["severity"] = TOPIC_SEVERITY_RULE.get(record.get("topic"), DEFAULT_SEVERITY)
        record["severity_source"] = "topic-rule"
        if not record.get("is_loophole"):
            # A compliant clause has no violation to grade.
            record["severity"] = "n/a"
            record["severity_source"] = "not-applicable"
    return records


def build_dataset(path=BENCHMARK_PATH):
    benchmark = load_benchmark(path)
    records = resolve_gold_evidence(benchmark["clauses"])
    return add_derived_severity(records)


def summarize(records):
    topics = {}
    severities = {}
    for record in records:
        topics[record["topic"]] = topics.get(record["topic"], 0) + 1
        severities[record["severity"]] = severities.get(record["severity"], 0) + 1

    loopholes = sum(1 for record in records if record["is_loophole"])
    return {
        "total_clauses": len(records),
        "loophole": loopholes,
        "compliant": len(records) - loopholes,
        "distinct_topics": len(topics),
        "topics": dict(sorted(topics.items())),
        "severity_distribution": dict(sorted(severities.items())),
        "severity_source": "derived from a documented topic rule, not annotated",
        "gold_evidence_pages": sum(len(record["gold_pages"]) for record in records),
        "distinct_gold_documents": len(
            {page["document"] for record in records for page in record["gold_pages"]}
        ),
    }


_passage_lookup = None


def _passages_by_id():
    global _passage_lookup
    if _passage_lookup is None:
        _passage_lookup = {}
        for passage in provenance.load_curated_passages():
            passage_id = passage.get("passage_id")
            if passage_id:
                _passage_lookup.setdefault(passage_id, []).append(passage)
    return _passage_lookup


def gold_page_set(record):
    """The set of ``(document, page)`` pairs that count as correct for a clause."""
    return {(page["document"], page["page"]) for page in record["gold_pages"]}


