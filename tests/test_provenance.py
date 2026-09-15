"""The join between indexed chunks and the reviewed RBI passages.

This join is what makes a citation possible at all: without it a finding can only
name a PDF, and the retrieval evaluation has no gold evidence to score against.
"""

import pytest

from src.retrieval import provenance


def test_curated_corpus_loads(curated_passages):
    assert len(curated_passages) == 57
    assert {"passage_id", "source_document", "page", "section", "status"} <= set(curated_passages[0])


def test_known_page_resolves_to_a_passage():
    """A page carrying a curated passage always reports its id."""
    block = provenance.describe("RBI_digital_Guidline2.pdf", 3)
    assert block["passage_id"]
    assert block["section"]
    assert block["document"] == "RBI_digital_Guidline2.pdf"
    assert block["page"] == 3


def test_page_without_a_curated_passage_still_cites_the_page():
    """Coverage is partial, so an unmatched page must degrade to document + page."""
    block = provenance.describe("RBI_Floating_Rate_Personal_Loan.pdf", 9999)
    assert block["passage_id"] is None
    assert block["document"] == "RBI_Floating_Rate_Personal_Loan.pdf"
    assert block["page"] == 9999
    assert block["citation"] == "RBI_Floating_Rate_Personal_Loan.pdf p.9999"


def test_every_curated_passage_page_exists_in_the_index(corpus):
    """The join only holds if both corpora agree on page numbering."""
    regulatory_pages = {
        (document.metadata["source"], document.metadata["page"])
        for document in corpus
        if document.metadata.get("type") == "regulatory_pdf"
    }
    missing = [
        passage["passage_id"]
        for passage in provenance.load_curated_passages()
        if (passage["source_document"], passage["page"]) not in regulatory_pages
    ]
    assert missing == []


def test_provenance_values_are_storable_by_chroma():
    """ChromaDB rejects nested objects, so every value has to be flat."""
    allowed = (str, int, float, bool, list, type(None))
    block = provenance.describe("RBI_digital_Guidline2.pdf", 3)
    for key, value in block.items():
        assert isinstance(value, allowed), f"{key} has type {type(value)}"


def test_from_metadata_round_trips():
    """The block rebuilt from stored metadata matches the one that was stored."""
    block = provenance.describe("RBI_digital_Guidline2.pdf", 3)
    metadata = {"source": "RBI_digital_Guidline2.pdf", "page": 3, **block}
    rebuilt = provenance.from_metadata(metadata)

    assert rebuilt["passage_id"] == block["passage_id"]
    assert rebuilt["section"] == block["section"]
    assert rebuilt["document"] == "RBI_digital_Guidline2.pdf"


def test_missing_page_is_handled():
    """A document-only chunk (a .docx) has no page and must not raise."""
    block = provenance.describe("SomePolicy.docx", None)
    assert block["page"] is None
    assert block["passage_id"] is None
    assert block["citation"] == "SomePolicy.docx"
