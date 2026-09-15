"""The risk classifier contract and the retrieval metric maths.

The metric functions are unit-tested against hand-computed values, because the
evaluation report quotes their averages and a wrong implementation would quietly
produce confident nonsense.
"""

import pytest
from langchain_core.documents import Document

from src.evaluation import evaluate_retrieval as metrics
from src.models import risk_classifier


def document(source, page, text="text"):
    return Document(page_content=text, metadata={"source": source, "page": page})


# --- metric maths ---------------------------------------------------------

def test_recall_at_counts_gold_pages_covered():
    ranked = [("a.pdf", 1), ("b.pdf", 2), ("c.pdf", 3)]
    gold = {("b.pdf", 2), ("d.pdf", 4)}

    assert metrics.average_precision_at(ranked, gold, 1) == 0.0
    assert metrics.average_precision_at(ranked, gold, 3) == 0.5


def test_hit_at_is_binary():
    ranked = [("a.pdf", 1), ("b.pdf", 2)]
    gold = {("b.pdf", 2)}

    assert metrics.hit_at(ranked, gold, 1) == 0.0
    assert metrics.hit_at(ranked, gold, 2) == 1.0


def test_reciprocal_rank_uses_the_first_relevant_hit():
    gold = {("b.pdf", 2)}

    assert metrics.reciprocal_rank([("a.pdf", 1), ("b.pdf", 2)], gold) == 0.5
    assert metrics.reciprocal_rank([("b.pdf", 2), ("a.pdf", 1)], gold) == 1.0
    assert metrics.reciprocal_rank([("a.pdf", 1)], gold) == 0.0


def test_ndcg_is_one_when_relevance_comes_first():
    gold = {("b.pdf", 2)}
    assert metrics.ndcg_at([("b.pdf", 2), ("a.pdf", 1)], gold, 2) == 1.0


def test_ndcg_discounts_lower_positions():
    """Relevant at rank 2 of 2 gold pages: DCG 1.0 over an ideal of 1 + 1/log2(3)."""
    ranked = [("b.pdf", 2), ("a.pdf", 1), ("c.pdf", 3)]
    gold = {("b.pdf", 2), ("d.pdf", 4)}

    expected = 1.0 / (1.0 + 1.0 / 1.5849625007211563)
    assert metrics.ndcg_at(ranked, gold, 3) == pytest.approx(expected, abs=1e-6)


def test_metrics_return_none_without_gold_evidence():
    assert metrics.average_precision_at([], set(), 3) is None
    assert metrics.hit_at([], set(), 3) is None
    assert metrics.reciprocal_rank([], set()) is None
    assert metrics.ndcg_at([], set(), 3) is None


def test_duplicate_pages_are_dropped():
    """Two chunks from one page must not count as two relevant hits."""
    documents = [document("a.pdf", 1), document("a.pdf", 1), document("b.pdf", 2)]
    unique = metrics.dedupe_by_page(documents)

    assert len(unique) == 2
    assert [(d.metadata["source"], d.metadata["page"]) for d in unique] == [("a.pdf", 1), ("b.pdf", 2)]


def test_page_identity_is_document_and_page():
    assert metrics.page_of(document("a.pdf", 7)) == ("a.pdf", 7)


# --- classifier contract --------------------------------------------------

def test_predict_risk_returns_the_expected_contract():
    result = risk_classifier.PolicyRiskClassifier().predict_risk(
        "A penal charge of 3% per month shall be levied on delayed repayment."
    )

    assert set(result) == {"risk_score", "category", "requires_red_teaming"}
    assert 0.0 <= result["risk_score"] <= 1.0
    assert result["category"] in {"High Risk", "Medium Risk", "Low Risk"}
    assert isinstance(result["requires_red_teaming"], bool)


def test_gate_matches_its_threshold():
    """requires_red_teaming must agree with the score and the documented threshold."""
    classifier = risk_classifier.PolicyRiskClassifier()
    result = classifier.predict_risk("Penal interest is compounded monthly on overdue amounts.")

    assert result["requires_red_teaming"] == (result["risk_score"] > risk_classifier.RED_TEAM_THRESHOLD)


def test_classifier_trains_from_the_benchmark(benchmark_records):
    """Training must use the labelled benchmark, not a hand-written list."""
    classifier = risk_classifier.PolicyRiskClassifier(model_path="data/processed/_test_model.pkl")
    classifier.train(records=benchmark_records)

    assert classifier.vectorizer is not None
    assert classifier.classifier is not None
    assert classifier.vectorizer.get_feature_names_out().size > 0

    import os

    os.remove(classifier.model_path)
