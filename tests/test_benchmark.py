"""The labelled benchmark and its ground truth.

If these break, every metric in the evaluation becomes meaningless.
"""

from src.evaluation import benchmark


def test_benchmark_is_loaded_and_balanced(benchmark_records):
    assert len(benchmark_records) == 24
    loopholes = [record for record in benchmark_records if record["is_loophole"]]
    assert len(loopholes) == 12


def test_every_clause_has_gold_evidence(benchmark_records):
    """A clause with no resolvable gold passage cannot be scored."""
    missing = [record["clause_id"] for record in benchmark_records if not record["gold_pages"]]
    assert missing == []


def test_gold_evidence_points_at_real_documents(benchmark_records):
    documents = {page["document"] for record in benchmark_records for page in record["gold_pages"]}
    assert documents == {"RBI_Penal_Charges_2023.pdf", "RBI_digital_Guidline2.pdf"}


def test_gold_evidence_carries_a_passage_id_and_page(benchmark_records):
    for record in benchmark_records:
        for page in record["gold_pages"]:
            assert page["passage_id"]
            assert isinstance(page["page"], int)


def test_splits_are_present(benchmark_records):
    splits = {record["split"] for record in benchmark_records}
    assert splits == {"train", "dev", "test"}


def test_derived_severity_is_labelled_as_derived(benchmark_records):
    """Severity is not annotated, and must never look like it is."""
    for record in benchmark_records:
        assert record["severity_source"] in {"topic-rule", "not-applicable"}
        assert record["severity"] in {"High", "Medium", "Low", "n/a"}


def test_compliant_clauses_are_not_given_a_severity(benchmark_records):
    for record in benchmark_records:
        if not record["is_loophole"]:
            assert record["severity"] == "n/a"


def test_summary_counts_match_the_records(benchmark_records):
    summary = benchmark.summarize(benchmark_records)
    assert summary["total_clauses"] == 24
    assert summary["loophole"] + summary["compliant"] == 24
    assert summary["distinct_topics"] > 1
    assert "derived" in summary["severity_source"]


def test_gold_page_set_is_a_set_of_document_page_pairs(benchmark_records):
    for record in benchmark_records:
        gold = benchmark.gold_page_set(record)
        assert gold
        for document, page in gold:
            assert isinstance(document, str)
            assert isinstance(page, int)
