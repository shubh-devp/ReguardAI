"""Agent-side safety behaviour, without calling any model.

The regression these lock down is the fail-closed guarantee: the pipeline claims
to reject unverified evidence, and a "false" string used to be read as a "true".
"""

import pytest
from langchain_core.documents import Document

from src.agents.auditor import build_evidence
from src.agents.llm import as_bool


@pytest.mark.parametrize("value", ["false", "False", "FALSE", "no", "0", "", "maybe"])
def test_falsy_strings_are_not_treated_as_true(value):
    """bool("false") is True in Python, which inverted the verifier's verdict."""
    assert as_bool(value) is False


@pytest.mark.parametrize("value", ["true", "True", "TRUE", "yes", "1"])
def test_truthy_strings_are_read_as_true(value):
    assert as_bool(value) is True


@pytest.mark.parametrize(
    "value,expected",
    [(True, True), (False, False), (1, True), (0, False), (None, False)],
)
def test_native_values_are_preserved(value, expected):
    assert as_bool(value) is expected


def test_evidence_block_reports_the_citation():
    documents = [
        Document(
            page_content="Penal charges shall not be levied as penal interest.",
            metadata={
                "source": "RBI_Penal_Charges_2023.pdf",
                "page": 11,
                "citation": "RBI_Penal_Charges_2023.pdf p.11",
                "passage_id": "RBI-PENAL-0004",
                "section": "Para 3(ii)",
                "status": "active",
            },
        ),
        Document(
            page_content="Another passage.",
            metadata={"source": "RBI_digital_Guidline2.pdf", "page": 3},
        ),
    ]

    block = build_evidence(documents)

    assert block["citation"] == "RBI_Penal_Charges_2023.pdf p.11"
    assert block["passage_id"] == "RBI-PENAL-0004"
    assert block["section"] == "Para 3(ii)"
    assert block["passage_text"].startswith("Penal charges")
    assert len(block["candidates"]) == 2
    assert block["candidates"][1]["document"] == "RBI_digital_Guidline2.pdf"


def test_evidence_reports_at_most_three_candidates():
    documents = [
        Document(page_content=f"passage {index}", metadata={"source": "a.pdf", "page": index})
        for index in range(1, 8)
    ]

    block = build_evidence(documents)
    assert len(block["candidates"]) == 3


def test_evidence_candidates_are_snippets_not_whole_passages():
    documents = [
        Document(page_content="x" * 5000, metadata={"source": "a.pdf", "page": 1}),
    ]

    block = build_evidence(documents)
    assert len(block["candidates"][0]["snippet"]) < 5000
    # The cited passage itself is kept whole, since it is the evidence.
    assert len(block["passage_text"]) == 5000
