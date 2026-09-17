"""Agent-side safety behaviour, without calling any model.

The regression these lock down is the fail-closed guarantee: the pipeline claims
to reject unverified evidence, and a "false" string used to be read as a "true".
The red team and re-test tests are pure functions over their inputs, because the
behaviour worth pinning down is the aggregation rule, not the model.
"""

import pytest
from langchain_core.documents import Document
from types import SimpleNamespace

from src.agents import auditor as auditor_module
from src.agents import challenger, retest, verifier
from src.agents.auditor import RegulatoryAuditor, align_verdicts, build_evidence
from src.agents.llm import align_by_index, as_bool
from src.agents.retest import ReTestAgent
from src.agents.verifier import aligned_verifications


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
    # The cited passage is not repeated among its own alternatives.
    assert len(block["candidates"]) == 1
    assert block["candidates"][0]["document"] == "RBI_digital_Guidline2.pdf"


def test_the_cited_passage_is_not_listed_as_its_own_alternative():
    """Listing the citation in "also retrieved" reads as a duplicate."""
    documents = [
        Document(page_content="first", metadata={"source": "a.pdf", "page": 1}),
        Document(page_content="second", metadata={"source": "b.pdf", "page": 2}),
        Document(page_content="third", metadata={"source": "c.pdf", "page": 3}),
    ]

    block = build_evidence(documents)

    assert [c["document"] for c in block["candidates"]] == ["b.pdf", "c.pdf"]


def test_evidence_reports_at_most_three_candidates():
    documents = [
        Document(page_content=f"passage {index}", metadata={"source": "a.pdf", "page": index})
        for index in range(1, 8)
    ]

    block = build_evidence(documents)
    assert len(block["candidates"]) == 3


def test_evidence_candidates_are_snippets_not_whole_passages():
    documents = [
        Document(page_content="the cited passage", metadata={"source": "cited.pdf", "page": 1}),
        Document(page_content="x" * 5000, metadata={"source": "a.pdf", "page": 2}),
    ]

    block = build_evidence(documents)
    assert len(block["candidates"][0]["snippet"]) < 5000
    # The cited passage itself is kept whole, since it is the evidence.
    assert block["passage_text"] == "the cited passage"


def test_evidence_carries_the_currency_of_the_cited_passage():
    """Every finding states how current the passage behind it is."""
    documents = [
        Document(
            page_content="An extract.",
            metadata={
                "source": "RBI_Penal_Charges_2023.pdf",
                "page": 11,
                "status": "active",
                "passage_id": "RBI-PENAL-0004",
            },
        )
    ]

    block = build_evidence(documents)
    assert block["currency"]["status"] == "active"
    assert block["currency"]["status_inactive"] is False
    assert isinstance(block["currency"]["warnings"], list)


def attack(surface, severity, detected=True, failed=False):
    return {
        "surface": surface,
        "title": surface,
        "vulnerability_detected": detected,
        "severity": severity,
        "attack_scenario": f"{surface} scenario",
        "explanation": "",
        "failed": failed,
    }


def test_all_surfaces_reporting_clear_is_recorded_as_unanimous():
    summary = challenger.summarise([attack("a", "Low", detected=False) for _ in range(4)])
    assert summary["consensus"] == "unanimous_clear"
    assert summary["surfaces_flagged"] == 0
    assert summary["agreement"] == 0.0


def test_a_split_red_team_is_reported_rather_than_averaged_away():
    """One surface finding a loophole is exactly the case a reviewer must see."""
    attacks = [attack("a", "High"), attack("b", "Low", detected=False), attack("c", "Low", detected=False)]

    summary = challenger.summarise(attacks)

    assert summary["consensus"] == "split"
    assert summary["agreement"] == 0.3333
    assert summary["flagged_surfaces"] == ["a"]


def test_a_failed_agent_is_listed_separately_from_a_clear_one():
    """An agent that errored did not clear the clause, so it must not look like it did."""
    attacks = [attack("a", "Low", detected=False), attack("b", "Low", detected=False, failed=True)]

    summary = challenger.summarise(attacks)

    assert summary["failed_surfaces"] == ["b"]
    assert summary["surfaces_flagged"] == 0


def test_every_surface_flagged_is_unanimous_vulnerable():
    summary = challenger.summarise([attack("a", "High"), attack("b", "Medium")])
    assert summary["consensus"] == "unanimous_vulnerable"
    assert summary["highest_severity"] == "High"


def test_the_primary_attack_is_the_most_severe_one():
    attacks = [attack("disclosure", "Low"), attack("charges", "High"), attack("cooling_off", "Medium")]
    assert challenger.select_primary(attacks)["surface"] == "charges"


def test_ties_break_on_the_declared_surface_order():
    """Determinism matters: the same clause must always pick the same attack."""
    attacks = [attack("data_consent", "High"), attack("disclosure", "High")]
    assert challenger.select_primary(attacks)["surface"] == "disclosure"


def test_nothing_is_primary_when_no_surface_flags_a_vulnerability():
    assert challenger.select_primary([attack("a", "Low", detected=False)]) is None


@pytest.mark.parametrize(
    "original,patched,expected",
    [
        (0, 0, "no_vulnerability_detected"),
        (3, 0, "fully_mitigated"),
        (3, 1, "partially_mitigated"),
        (2, 2, "not_mitigated"),
        (1, 2, "not_mitigated"),
    ],
)
def test_the_verdict_distinguishes_fixed_from_never_vulnerable(original, patched, expected):
    """The old code called a partial reduction a pass, and a no-op a pass too."""
    assert ReTestAgent._verdict(original, patched, 4, 4) == expected


def test_nothing_measured_is_not_the_same_as_nothing_vulnerable():
    """A rate-limited call is not evidence that the attack was blocked."""
    assert ReTestAgent._verdict(0, 0, 0, 0) == "not_measured"
    assert ReTestAgent._verdict(3, 0, 4, 0) == "not_measured"
    assert ReTestAgent._verdict(3, 0, 0, 4) == "not_measured"


def test_remediation_with_no_attacks_is_not_measured_rather_than_passed():
    report = ReTestAgent().evaluate_patch("original", "patched", attacks=[])

    assert report["verdict"] == "not_measured"
    assert report["retest_passed"] is False
    assert report["asr_before"] is None
    assert report["remediation_success_rate"] is None


def test_an_unmeasurable_attack_is_excluded_from_the_asr(monkeypatch):
    """A failed model call must not be counted as a blocked attack."""
    agent = ReTestAgent.__new__(ReTestAgent)  # no retriever or model needed
    verdicts = {"original": [True, None, True], "patched": [False, None, False]}
    monkeypatch.setattr(agent, "judge_clause", lambda clause, attacks: verdicts[clause])

    report = agent.evaluate_patch("original", "patched", attacks=[attack("a", "High")] * 3)

    assert report["asr_before"] == 1.0
    assert report["asr_after"] == 0.0
    assert report["unmeasured_attacks"] == 1
    assert report["measured_attacks"] == 2
    assert report["measurement_complete"] is False
    # A clean sweep on the measured attacks is still not a pass while one attack
    # was never measured.
    assert report["verdict"] == "fully_mitigated"
    assert report["retest_passed"] is False


def test_an_attack_counts_only_when_the_citation_behind_it_is_supported(monkeypatch):
    """One auditor verdict and one verifier verdict have to agree per attack."""
    agent = ReTestAgent.__new__(ReTestAgent)
    agent.auditor = SimpleNamespace(
        audit_clause_batch=lambda clause, attacks: {
            "findings": [
                {"violation_confirmed": True},
                {"violation_confirmed": True},
                {"violation_confirmed": False},
            ],
            "evidence": [{"passage_text": "p1"}, {"passage_text": "p2"}, {"passage_text": "p3"}],
            "error": False,
        }
    )
    monkeypatch.setattr(
        retest,
        "verify_evidence_batch",
        lambda clause, claims, passages: {
            "verdicts": [
                {"is_supported": True},    # auditor yes, verifier yes -> defeats the clause
                {"is_supported": False},   # auditor yes, verifier no  -> does not count
                {"is_supported": True},    # auditor no                -> does not count
            ],
            "error": False,
        },
    )

    judged = agent.judge_clause("clause", [attack("a", "High")] * 3)

    assert judged == [True, False, False]


def test_each_claim_is_verified_against_its_own_evidence(monkeypatch):
    """The verifier must see the passage each claim was judged on, in order."""
    agent = ReTestAgent.__new__(ReTestAgent)
    agent.auditor = SimpleNamespace(
        audit_clause_batch=lambda clause, attacks: {
            "findings": [{"violation_confirmed": True}, {"violation_confirmed": True}],
            "evidence": [{"passage_text": "PASSAGE-A"}, {"passage_text": "PASSAGE-B"}],
            "error": False,
        }
    )
    seen = {}

    def fake_batch(clause, claims, passages):
        seen["passages"] = passages
        return {"verdicts": [{"is_supported": True}, {"is_supported": True}], "error": False}

    monkeypatch.setattr(retest, "verify_evidence_batch", fake_batch)

    agent.judge_clause("clause", [attack("a", "High")] * 2)

    assert seen["passages"] == ["PASSAGE-A", "PASSAGE-B"]


def test_a_failed_auditor_call_leaves_every_attack_unmeasured(monkeypatch):
    """A broken call is not a set of blocked attacks."""
    agent = ReTestAgent.__new__(ReTestAgent)
    agent.auditor = SimpleNamespace(
        audit_clause_batch=lambda clause, attacks: {"findings": [], "evidence": [], "error": True}
    )

    assert agent.judge_clause("clause", [attack("a", "High")] * 2) == [None, None]


def test_a_short_batch_reply_leaves_the_rest_unmeasured(monkeypatch):
    """A model that answers about one attack has not cleared the other three."""
    agent = ReTestAgent.__new__(ReTestAgent)
    agent.auditor = SimpleNamespace(
        audit_clause_batch=lambda clause, attacks: {
            "findings": [{"violation_confirmed": True}, None, None, None],
            "evidence": [{"passage_text": "p"}] * 4,
            "error": False,
        }
    )
    monkeypatch.setattr(
        retest,
        "verify_evidence_batch",
        lambda clause, claims, passages: {
            "verdicts": [{"is_supported": True}, None, None, None],
            "error": False,
        },
    )

    judged = agent.judge_clause("clause", [attack("a", "High")] * 4)

    assert judged == [True, None, None, None]


# Batching the judging must not batch the retrieval. Judging a data-consent attack
# against a penal-charges passage would clear it for the wrong reason, and a
# red-teaming tool that under-reports is failing in the dangerous direction.


def test_each_attack_is_judged_against_its_own_retrieved_evidence(monkeypatch):
    auditor = RegulatoryAuditor.__new__(RegulatoryAuditor)
    by_scenario = {
        "cooling-off scenario": "COOLING OFF PASSAGE",
        "data consent scenario": "DATA CONSENT PASSAGE",
    }

    def fake_retrieve(query):
        for scenario, passage in by_scenario.items():
            if scenario in query:
                return {"passage_text": passage}, passage, "doc.pdf"
        return {"passage_text": "FALLBACK"}, "FALLBACK", "doc.pdf"

    auditor.retrieve = fake_retrieve
    monkeypatch.setattr(auditor_module, "ensure_api_key", lambda: None)

    captured = {}

    def fake_generate_json(prompt, **kwargs):
        captured["prompt"] = prompt
        return {"verdicts": []}

    monkeypatch.setattr(auditor_module, "generate_json", fake_generate_json)

    attacks = [
        {"surface": "cooling_off", "severity": "Low", "attack_scenario": "cooling-off scenario"},
        {"surface": "data_consent", "severity": "Low", "attack_scenario": "data consent scenario"},
    ]

    result = auditor.audit_clause_batch("Some policy clause.", attacks)

    assert "COOLING OFF PASSAGE" in captured["prompt"]
    assert "DATA CONSENT PASSAGE" in captured["prompt"]
    # And the evidence comes back per attack, so the verifier can use the right one.
    assert [block["passage_text"] for block in result["evidence"]] == [
        "COOLING OFF PASSAGE",
        "DATA CONSENT PASSAGE",
    ]


def test_each_per_attack_row_carries_its_readable_name(monkeypatch):
    """The report must not print a raw internal key like "cooling_off" at the user."""
    agent = ReTestAgent.__new__(ReTestAgent)
    monkeypatch.setattr(agent, "judge_clause", lambda clause, attacks: [False] * len(attacks))

    report = agent.evaluate_patch(
        "original",
        "patched",
        attacks=[
            {
                "surface": "cooling_off",
                "title": "Cooling-off and exit rights",
                "severity": "High",
                "attack_scenario": "scenario",
            }
        ],
    )

    assert report["per_attack"][0]["title"] == "Cooling-off and exit rights"
    assert report["per_attack"][0]["surface"] == "cooling_off"


def test_the_verifier_refuses_a_claim_evidence_count_mismatch(monkeypatch):
    """Verifying a claim against the wrong passage is worse than not verifying."""
    monkeypatch.setattr(verifier, "ensure_api_key", lambda: None)

    result = verifier.verify_evidence_batch("clause", [{"a": 1}, {"b": 2}], ["only one passage"])

    assert result["error"] is True
    assert result["verdicts"] == [None, None]



def test_verdicts_are_placed_by_their_reported_index():
    """A reply that comes back out of order must not shift the verdicts."""
    reply = [{"index": 1, "is_supported": True}, {"index": 0, "is_supported": False}]

    aligned = align_by_index(reply, 2)

    assert aligned[0]["is_supported"] is False
    assert aligned[1]["is_supported"] is True


def test_a_missing_verdict_is_left_unmeasured_not_defaulted():
    """Padding a short reply would invent verdicts the model never gave."""
    aligned = align_by_index([{"index": 0, "is_supported": True}], 3)

    assert aligned[0]["is_supported"] is True
    assert aligned[1] is None
    assert aligned[2] is None


def test_a_duplicate_index_does_not_overwrite_the_first_answer():
    reply = [{"index": 0, "note": "first"}, {"index": 0, "note": "duplicate"}]

    aligned = align_by_index(reply, 2)

    assert aligned[0]["note"] == "first"
    assert aligned[1] is None


def test_a_missing_or_out_of_range_index_falls_back_to_position():
    """Sloppy formatting should not throw away an otherwise usable reply."""
    assert align_by_index([{"is_supported": True}], 1)[0]["is_supported"] is True
    assert align_by_index([{"index": 99, "is_supported": True}], 1)[0]["is_supported"] is True


def test_a_non_list_reply_aligned_to_nothing():
    assert align_by_index({"index": 0}, 2) == [None, None]


def test_the_auditor_alignment_coerces_and_defaults_the_severity():
    """An unexpected severity must not leak through as a free-text label."""
    aligned = align_verdicts(
        [{"index": 0, "violation_confirmed": "true", "severity": "catastrophic"}], 1
    )

    assert aligned[0]["violation_confirmed"] is True
    assert aligned[0]["severity"] == "Medium"


def test_the_verifier_alignment_defaults_confidence_to_zero():
    """A missing or wrong-typed confidence is reported as no confidence, not one."""
    aligned = aligned_verifications(
        [{"index": 0, "is_supported": True, "confidence_score": "high"}], 1
    )

    assert aligned[0]["is_supported"] is True
    assert aligned[0]["confidence_score"] == 0.0







# """Unit test suite for agent-side safety guarantees and pure logic functions."""

# import pytest
# from langchain_core.documents import Document
# from types import SimpleNamespace

# from src.agents import auditor as auditor_module
# from src.agents import challenger, retest, verifier
# from src.agents.auditor import RegulatoryAuditor, align_verdicts, build_evidence
# from src.agents.llm import align_by_index, as_bool
# from src.agents.retest import ReTestAgent
# from src.agents.verifier import aligned_verifications


# @pytest.mark.parametrize("value", ["false", "False", "FALSE", "no", "0", "", "maybe"])
# def test_falsy_strings_are_not_treated_as_true(value):
#     """Ensure falsy text representations evaluate to boolean False."""
#     assert as_bool(value) is False


# @pytest.mark.parametrize("value", ["true", "True", "TRUE", "yes", "1"])
# def test_truthy_strings_are_read_as_true(value):
#     assert as_bool(value) is True


# @pytest.mark.parametrize(
#     "value,expected",
#     [(True, True), (False, False), (1, True), (0, False), (None, False)],
# )
# def test_native_values_are_preserved(value, expected):
#     assert as_bool(value) is expected


# def test_evidence_block_reports_the_citation():
#     documents = [
#         Document(
#             page_content="Penal charges shall not be levied as penal interest.",
#             metadata={
#                 "source": "RBI_Penal_Charges_2023.pdf",
#                 "page": 11,
#                 "citation": "RBI_Penal_Charges_2023.pdf p.11",
#                 "passage_id": "RBI-PENAL-0004",
#                 "section": "Para 3(ii)",
#                 "status": "active",
#             },
#         ),
#         Document(
#             page_content="Another passage.",
#             metadata={"source": "RBI_digital_Guidline2.pdf", "page": 3},
#         ),
#     ]

#     block = build_evidence(documents)

#     assert block["citation"] == "RBI_Penal_Charges_2023.pdf p.11"
#     assert block["passage_id"] == "RBI-PENAL-0004"
#     assert block["section"] == "Para 3(ii)"
#     assert block["passage_text"].startswith("Penal charges")
#     assert len(block["candidates"]) == 1
#     assert block["candidates"][0]["document"] == "RBI_digital_Guidline2.pdf"


# def test_the_cited_passage_is_not_listed_as_its_own_alternative():
#     documents = [
#         Document(page_content="first", metadata={"source": "a.pdf", "page": 1}),
#         Document(page_content="second", metadata={"source": "b.pdf", "page": 2}),
#         Document(page_content="third", metadata={"source": "c.pdf", "page": 3}),
#     ]

#     block = build_evidence(documents)
#     assert [c["document"] for c in block["candidates"]] == ["b.pdf", "c.pdf"]


# def test_evidence_reports_at_most_three_candidates():
#     documents = [
#         Document(page_content=f"passage {index}", metadata={"source": "a.pdf", "page": index})
#         for index in range(1, 8)
#     ]

#     block = build_evidence(documents)
#     assert len(block["candidates"]) == 3


# def test_evidence_candidates_are_snippets_not_whole_passages():
#     documents = [
#         Document(page_content="the cited passage", metadata={"source": "cited.pdf", "page": 1}),
#         Document(page_content="x" * 5000, metadata={"source": "a.pdf", "page": 2}),
#     ]

#     block = build_evidence(documents)
#     assert len(block["candidates"][0]["snippet"]) < 5000
#     assert block["passage_text"] == "the cited passage"


# def test_evidence_carries_the_currency_of_the_cited_passage():
#     documents = [
#         Document(
#             page_content="An extract.",
#             metadata={
#                 "source": "RBI_Penal_Charges_2023.pdf",
#                 "page": 11,
#                 "status": "active",
#                 "passage_id": "RBI-PENAL-0004",
#             },
#         )
#     ]

#     block = build_evidence(documents)
#     assert block["currency"]["status"] == "active"
#     assert block["currency"]["status_inactive"] is False
#     assert isinstance(block["currency"]["warnings"], list)


# def attack(surface, severity, detected=True, failed=False):
#     return {
#         "surface": surface,
#         "title": surface,
#         "vulnerability_detected": detected,
#         "severity": severity,
#         "attack_scenario": f"{surface} scenario",
#         "explanation": "",
#         "failed": failed,
#     }


# def test_all_surfaces_reporting_clear_is_recorded_as_unanimous():
#     summary = challenger.summarise([attack("a", "Low", detected=False) for _ in range(4)])
#     assert summary["consensus"] == "unanimous_clear"
#     assert summary["surfaces_flagged"] == 0
#     assert summary["agreement"] == 0.0


# def test_a_split_red_team_is_reported_rather_than_averaged_away():
#     attacks = [attack("a", "High"), attack("b", "Low", detected=False), attack("c", "Low", detected=False)]
#     summary = challenger.summarise(attacks)

#     assert summary["consensus"] == "split"
#     assert summary["agreement"] == 0.3333
#     assert summary["flagged_surfaces"] == ["a"]


# def test_a_failed_agent_is_listed_separately_from_a_clear_one():
#     attacks = [attack("a", "Low", detected=False), attack("b", "Low", detected=False, failed=True)]
#     summary = challenger.summarise(attacks)

#     assert summary["failed_surfaces"] == ["b"]
#     assert summary["surfaces_flagged"] == 0


# def test_every_surface_flagged_is_unanimous_vulnerable():
#     summary = challenger.summarise([attack("a", "High"), attack("b", "Medium")])
#     assert summary["consensus"] == "unanimous_vulnerable"
#     assert summary["highest_severity"] == "High"


# def test_the_primary_attack_is_the_most_severe_one():
#     attacks = [attack("disclosure", "Low"), attack("charges", "High"), attack("cooling_off", "Medium")]
#     assert challenger.select_primary(attacks)["surface"] == "charges"


# def test_ties_break_on_the_declared_surface_order():
#     attacks = [attack("data_consent", "High"), attack("disclosure", "High")]
#     assert challenger.select_primary(attacks)["surface"] == "disclosure"


# def test_nothing_is_primary_when_no_surface_flags_a_vulnerability():
#     assert challenger.select_primary([attack("a", "Low", detected=False)]) is None


# @pytest.mark.parametrize(
#     "original,patched,expected",
#     [
#         (0, 0, "no_vulnerability_detected"),
#         (3, 0, "fully_mitigated"),
#         (3, 1, "partially_mitigated"),
#         (2, 2, "not_mitigated"),
#         (1, 2, "not_mitigated"),
#     ],
# )
# def test_the_verdict_distinguishes_fixed_from_never_vulnerable(original, patched, expected):
#     assert ReTestAgent._verdict(original, patched, 4, 4) == expected


# def test_nothing_measured_is_not_the_same_as_nothing_vulnerable():
#     assert ReTestAgent._verdict(0, 0, 0, 0) == "not_measured"
#     assert ReTestAgent._verdict(3, 0, 4, 0) == "not_measured"
#     assert ReTestAgent._verdict(3, 0, 0, 4) == "not_measured"


# def test_remediation_with_no_attacks_is_not_measured_rather_than_passed():
#     report = ReTestAgent().evaluate_patch("original", "patched", attacks=[])
#     assert report["verdict"] == "not_measured"
#     assert report["retest_passed"] is False
#     assert report["asr_before"] is None
#     assert report["remediation_success_rate"] is None


# def test_an_unmeasurable_attack_is_excluded_from_the_asr(monkeypatch):
#     agent = ReTestAgent.__new__(ReTestAgent)
#     verdicts = {"original": [True, None, True], "patched": [False, None, False]}
#     monkeypatch.setattr(agent, "judge_clause", lambda clause, attacks: verdicts[clause])

#     report = agent.evaluate_patch("original", "patched", attacks=[attack("a", "High")] * 3)

#     assert report["asr_before"] == 1.0
#     assert report["asr_after"] == 0.0
#     assert report["unmeasured_attacks"] == 1
#     assert report["measured_attacks"] == 2
#     assert report["measurement_complete"] is False
#     assert report["verdict"] == "fully_mitigated"
#     assert report["retest_passed"] is False


# def test_an_attack_counts_only_when_the_citation_behind_it_is_supported(monkeypatch):
#     agent = ReTestAgent.__new__(ReTestAgent)
#     agent.auditor = SimpleNamespace(
#         audit_clause_batch=lambda clause, attacks: {
#             "findings": [
#                 {"violation_confirmed": True},
#                 {"violation_confirmed": True},
#                 {"violation_confirmed": False},
#             ],
#             "evidence": [{"passage_text": "p1"}, {"passage_text": "p2"}, {"passage_text": "p3"}],
#             "error": False,
#         }
#     )
#     monkeypatch.setattr(
#         retest,
#         "verify_evidence_batch",
#         lambda clause, claims, passages: {
#             "verdicts": [
#                 {"is_supported": True},
#                 {"is_supported": False},
#                 {"is_supported": True},
#             ],
#             "error": False,
#         },
#     )

#     judged = agent.judge_clause("clause", [attack("a", "High")] * 3)
#     assert judged == [True, False, False]


# def test_each_claim_is_verified_against_its_own_evidence(monkeypatch):
#     agent = ReTestAgent.__new__(ReTestAgent)
#     agent.auditor = SimpleNamespace(
#         audit_clause_batch=lambda clause, attacks: {
#             "findings": [{"violation_confirmed": True}, {"violation_confirmed": True}],
#             "evidence": [{"passage_text": "PASSAGE-A"}, {"passage_text": "PASSAGE-B"}],
#             "error": False,
#         }
#     )
#     seen = {}

#     def fake_batch(clause, claims, passages):
#         seen["passages"] = passages
#         return {"verdicts": [{"is_supported": True}, {"is_supported": True}], "error": False}

#     monkeypatch.setattr(retest, "verify_evidence_batch", fake_batch)
#     agent.judge_clause("clause", [attack("a", "High")] * 2)
#     assert seen["passages"] == ["PASSAGE-A", "PASSAGE-B"]


# def test_a_failed_auditor_call_leaves_every_attack_unmeasured(monkeypatch):
#     agent = ReTestAgent.__new__(ReTestAgent)
#     agent.auditor = SimpleNamespace(
#         audit_clause_batch=lambda clause, attacks: {"findings": [], "evidence": [], "error": True}
#     )
#     assert agent.judge_clause("clause", [attack("a", "High")] * 2) == [None, None]


# def test_a_short_batch_reply_leaves_the_rest_unmeasured(monkeypatch):
#     agent = ReTestAgent.__new__(ReTestAgent)
#     agent.auditor = SimpleNamespace(
#         audit_clause_batch=lambda clause, attacks: {
#             "findings": [{"violation_confirmed": True}, None, None, None],
#             "evidence": [{"passage_text": "p"}] * 4,
#             "error": False,
#         }
#     )
#     monkeypatch.setattr(
#         retest,
#         "verify_evidence_batch",
#         lambda clause, claims, passages: {
#             "verdicts": [{"is_supported": True}, None, None, None],
#             "error": False,
#         },
#     )

#     judged = agent.judge_clause("clause", [attack("a", "High")] * 4)
#     assert judged == [True, None, None, None]


# def test_each_attack_is_judged_against_its_own_retrieved_evidence(monkeypatch):
#     auditor = RegulatoryAuditor.__new__(RegulatoryAuditor)
#     by_scenario = {
#         "cooling-off scenario": "COOLING OFF PASSAGE",
#         "data consent scenario": "DATA CONSENT PASSAGE",
#     }

#     def fake_retrieve(query):
#         for scenario, passage in by_scenario.items():
#             if scenario in query:
#                 return {"passage_text": passage}, passage, "doc.pdf"
#         return {"passage_text": "FALLBACK"}, "FALLBACK", "doc.pdf"

#     auditor.retrieve = fake_retrieve
#     monkeypatch.setattr(auditor_module, "ensure_api_key", lambda: None)

#     captured = {}

#     def fake_generate_json(prompt, **kwargs):
#         captured["prompt"] = prompt
#         return {"verdicts": []}

#     monkeypatch.setattr(auditor_module, "generate_json", fake_generate_json)

#     attacks = [
#         {"surface": "cooling_off", "severity": "Low", "attack_scenario": "cooling-off scenario"},
#         {"surface": "data_consent", "severity": "Low", "attack_scenario": "data consent scenario"},
#     ]

#     result = auditor.audit_clause_batch("Some policy clause.", attacks)

#     assert "COOLING OFF PASSAGE" in captured["prompt"]
#     assert "DATA CONSENT PASSAGE" in captured["prompt"]
#     assert [block["passage_text"] for block in result["evidence"]] == [
#         "COOLING OFF PASSAGE",
#         "DATA CONSENT PASSAGE",
#     ]


# def test_each_per_attack_row_carries_its_readable_name(monkeypatch):
#     agent = ReTestAgent.__new__(ReTestAgent)
#     monkeypatch.setattr(agent, "judge_clause", lambda clause, attacks: [False] * len(attacks))

#     report = agent.evaluate_patch(
#         "original",
#         "patched",
#         attacks=[
#             {
#                 "surface": "cooling_off",
#                 "title": "Cooling-off and exit rights",
#                 "severity": "High",
#                 "attack_scenario": "scenario",
#             }
#         ],
#     )

#     assert report["per_attack"][0]["title"] == "Cooling-off and exit rights"
#     assert report["per_attack"][0]["surface"] == "cooling_off"


# def test_the_verifier_refuses_a_claim_evidence_count_mismatch(monkeypatch):
#     monkeypatch.setattr(verifier, "ensure_api_key", lambda: None)
#     result = verifier.verify_evidence_batch("clause", [{"a": 1}, {"b": 2}], ["only one passage"])
#     assert result["error"] is True
#     assert result["verdicts"] == [None, None]


# def test_verdicts_are_placed_by_their_reported_index():
#     reply = [{"index": 1, "is_supported": True}, {"index": 0, "is_supported": False}]
#     aligned = align_by_index(reply, 2)
#     assert aligned[0]["is_supported"] is False
#     assert aligned[1]["is_supported"] is True


# def test_a_missing_verdict_is_left_unmeasured_not_defaulted():
#     aligned = align_by_index([{"index": 0, "is_supported": True}], 3)
#     assert aligned[0]["is_supported"] is True
#     assert aligned[1] is None
#     assert aligned[2] is None


# def test_a_duplicate_index_does_not_overwrite_the_first_answer():
#     reply = [{"index": 0, "note": "first"}, {"index": 0, "note": "duplicate"}]
#     aligned = align_by_index(reply, 2)
#     assert aligned[0]["note"] == "first"
#     assert aligned[1] is None


# def test_a_missing_or_out_of_range_index_falls_back_to_position():
#     assert align_by_index([{"is_supported": True}], 1)[0]["is_supported"] is True
#     assert align_by_index([{"index": 99, "is_supported": True}], 1)[0]["is_supported"] is True


# def test_a_non_list_reply_aligned_to_nothing():
#     assert align_by_index({"index": 0}, 2) == [None, None]


# def test_the_auditor_alignment_coerces_and_defaults_the_severity():
#     aligned = align_verdicts(
#         [{"index": 0, "violation_confirmed": "true", "severity": "catastrophic"}], 1
#     )
#     assert aligned[0]["violation_confirmed"] is True
#     assert aligned[0]["severity"] == "Medium"


# def test_the_verifier_alignment_defaults_confidence_to_zero():
#     aligned = aligned_verifications(
#         [{"index": 0, "is_supported": True, "confidence_score": "high"}], 1
#     )
#     assert aligned[0]["is_supported"] is True
#     assert aligned[0]["confidence_score"] == 0.0
