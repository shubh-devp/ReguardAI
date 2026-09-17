"""Regulatory Auditor agent: does this clause breach the retrieved RBI passage?

Two entry points, one judgement:

- ``audit_clause`` judges a single attack scenario.
- ``audit_clause_batch`` judges a whole attack set in one call.

The batch version exists because the re-test used to judge every attack with its
own call, which came to sixteen model calls for a single audit - more than the free
tier allows per minute. Judging is batched; retrieval is not. Retrieval is a local
search, so it costs nothing to give every attack the passage for its own surface,
and each verdict still rests on evidence that is actually about it.
"""

import json
import logging

from src.agents.llm import align_by_index, as_bool, ensure_api_key, generate_json
from src.retrieval import provenance, temporal
from src.retrieval.hybrid_retriever import load_chunks_from_json, build_chroma_hybrid_retriever

logger = logging.getLogger(__name__)

# How many retrieved candidates to report alongside the passage actually cited.
CANDIDATES_REPORTED = 3
SNIPPET_CHARS = 220
VERDICT_SEVERITIES = ("Low", "Medium", "High")
# Used when retrieval is unavailable. It is a placeholder, not evidence, and the
# evidence block says so.
FALLBACK_PASSAGE = "RBI/2023-24/53: Statutory regulatory guideline on penal charges."
FALLBACK_ID = "RBI-REF-01"
# A retrieval query is a handful of sentences; the cap stops a long clause plus a
# long attack set from turning into a huge embedding request.
QUERY_CHARS = 2000


def build_evidence(results):
    """Turn the retrieved chunks into a provenance block.

    A finding is only worth as much as the evidence behind it, so this records
    which document, page, section and passage id the decision rested on, plus the
    runner-up candidates that were considered.
    """
    top = results[0]
    block = provenance.from_metadata(top.metadata)
    block["passage_text"] = top.page_content
    # How current the cited passage is: effective date, lifecycle status, and
    # whether a newer passage of the same regulation has since been issued.
    block["currency"] = temporal.assess(block)
    block["candidates"] = [
        {
            "citation": document.metadata.get("citation"),
            "document": document.metadata.get("source"),
            "page": document.metadata.get("page"),
            "passage_id": document.metadata.get("passage_id"),
            "section": document.metadata.get("section"),
            "status": document.metadata.get("status"),
            "snippet": document.page_content[:SNIPPET_CHARS],
        }
        # The first result is the passage being cited, so the runner-up list starts
        # after it. Listing the citation as one of its own alternatives made the
        # "also retrieved" list look like it contained a duplicate.
        for document in results[1 : CANDIDATES_REPORTED + 1]
    ]
    return block


def empty_evidence():
    """The evidence block used when no passage could be retrieved."""
    return {
        "citation": None,
        "passage_id": None,
        "section": None,
        "passage_text": FALLBACK_PASSAGE,
        "currency": temporal.assess({}),
        "candidates": [],
        "retrieval_failed": False,
    }


def align_verdicts(verdicts, count):
    """Line a batched reply up with the attacks it was asked about.

    The model reports each verdict under an explicit index, so an answer that comes
    back reordered, short, or with a repeated index cannot be silently shifted onto
    the wrong attack. Anything not answered is left as ``None``, which callers read
    as "not measured" rather than as a clear verdict.
    """
    aligned = [None] * count
    for position, verdict in enumerate(verdicts):
        if not isinstance(verdict, dict):
            continue

        index = verdict.get("index", position)
        if not isinstance(index, int) or not 0 <= index < count:
            # A missing or out-of-range index is more likely to be sloppy
            # formatting than a real reordering, so fall back to the position.
            index = position
        if aligned[index] is not None:
            # A duplicate index would otherwise overwrite an earlier answer.
            continue

        severity = str(verdict.get("severity") or "").strip().title()
        aligned[index] = {
            "violation_confirmed": as_bool(verdict.get("violation_confirmed", False)),
            "severity": severity if severity in VERDICT_SEVERITIES else "Medium",
            "explanation": str(verdict.get("explanation") or "").strip(),
        }
    return aligned


def attack_text(attack):
    """The scenario string for one attack, replayed rather than paraphrased."""
    return attack.get("attack_scenario") or attack.get("title") or "Exploit regulatory loophole."


SINGLE_PROMPT = """
        You are the Regulatory Auditor Agent for Reguard AI, an enterprise RBI compliance engine.
        Analyze the given loan policy clause and adversarial attack scenario against the retrieved RBI statutory evidence.

        Policy Clause:
        "{clause_text}"

        Adversarial Attack Scenario / Loophole:
        {attack_scenario}

        Retrieved RBI Statutory Evidence:
        "{passage}"

        Task:
        1. Determine if the policy clause combined with the attack scenario violates RBI guidelines.
        2. Provide a clear regulatory explanation and severity level (Low, Medium, High).

        Return your response strictly as a valid JSON object with these exact keys:
        - "violation_confirmed": boolean (true if violation exists, false otherwise)
        - "severity": string ("Low", "Medium", "High")
        - "explanation": string (detailed regulatory reasoning)
        - "matched_rbi_passage_id": string ("{matched_id}")
        - "retrieved_passage": string (the exact retrieved RBI statutory evidence text provided above)

        Do not include markdown code block wrappers in your response, just raw JSON.
        """

BATCH_PROMPT = """
        You are the Regulatory Auditor Agent for Reguard AI, an enterprise RBI compliance engine.
        You are judging one loan policy clause against several independent attack
        scenarios. Each scenario comes with the RBI evidence retrieved for it. Judge
        every scenario only against its own evidence, and on its own - a verdict on
        one scenario must not influence another.

        Policy Clause:
        "{clause_text}"

        Attack Scenarios, each with the evidence retrieved for it and the index you
        must report it under:

        {blocks}

        Task:
        For every scenario, decide whether the clause combined with that scenario
        violates RBI guidelines, and give a severity level (Low, Medium, High). A
        scenario only counts as a violation if the evidence retrieved for that
        scenario actually supports it.

        Return your response strictly as a valid JSON object with one key "verdicts",
        whose value is an array holding exactly one entry per scenario, in the order
        given. Each entry must have these exact keys:
        - "index": integer, the index shown for that scenario
        - "violation_confirmed": boolean
        - "severity": string ("Low", "Medium", "High")
        - "explanation": string (detailed regulatory reasoning)

        Do not include markdown code block wrappers in your response, just raw JSON.
        """


class RegulatoryAuditor:
    """
    Regulatory Auditor Agent. Audits a policy clause against RBI guidelines
    retrieved via Hybrid RAG, returning violation status, severity, and the actual retrieved passage.
    """

    def __init__(self):
        try:
            docs = load_chunks_from_json()
            self.retriever = build_chroma_hybrid_retriever(docs)
        except Exception:
            #Falling back to a fixed passage is the safe behaviour, but it is
            #also silent evidence loss, so make the reason visible in the log.
            logger.exception("Retriever unavailable; audits will use a fixed passage")
            self.retriever = None

    def retrieve(self, query: str):
        """Retrieve regulatory evidence locally.

        Returns ``(evidence, passage_text, matched_id)``. Retrieval costs no model
        calls, so both the single and the batched audit can call it freely.
        """
        evidence = empty_evidence()
        passage_text = FALLBACK_PASSAGE
        matched_id = FALLBACK_ID

        if not self.retriever:
            return evidence, passage_text, matched_id

        try:
            results = self.retriever.invoke(query[:QUERY_CHARS])
            if results:
                evidence = build_evidence(results)
                passage_text = evidence["passage_text"]
                # Kept as the filename for backwards compatibility with the
                # existing audit trail; the precise citation is in `evidence`.
                matched_id = results[0].metadata.get("source", FALLBACK_ID)
        except Exception as error:
            logger.exception("RAG retrieval failed in the auditor")
            evidence["retrieval_failed"] = True
            evidence["retrieval_error"] = str(error)
            evidence["currency"] = temporal.assess({})

        return evidence, passage_text, matched_id

    def audit_clause(self, clause_text: str, attack_scenario: dict) -> dict:
        ensure_api_key()

        query = f"{clause_text} {attack_scenario.get('attack_scenario', '')}"
        evidence, retrieved_passage_text, matched_id = self.retrieve(query)

        prompt = SINGLE_PROMPT.format(
            clause_text=clause_text,
            attack_scenario=json.dumps(attack_scenario, indent=2),
            passage=retrieved_passage_text,
            matched_id=matched_id,
        )

        try:
            result = generate_json(prompt, temperature=0.1)

        except Exception as error:
            logger.error("Auditor agent failed: %s", error)
            return {
                "violation_confirmed": False,
                "severity": "Low",
                "explanation": f"Audit analysis failed due to error: {str(error)}",
                "matched_rbi_passage_id": matched_id,
                "retrieved_passage": retrieved_passage_text,
                "evidence": evidence,
                # A failed call is not the same as a clause that was cleared, and
                # the re-test has to be able to tell the two apart.
                "error": True,
            }

        # The retrieved text is authoritative, so it is not taken from the model.
        result["retrieved_passage"] = retrieved_passage_text
        result["matched_rbi_passage_id"] = matched_id
        result["evidence"] = evidence
        result["error"] = False
        return result

    def audit_clause_batch(self, clause_text: str, attacks: list) -> dict:
        """Judge a whole attack set against one clause in a single call.

        Same judgement as ``audit_clause``, batched: one model call for all the
        attacks instead of one per attack.

        Retrieval is deliberately *not* batched. It is local, so it costs no model
        calls, and every attack still gets the passage relevant to its own surface -
        the same passage the single-attack path would have used. Retrieving once for
        the whole set and judging all four attacks against it would put a
        data-consent attack up against a penal-charges passage and mark it clear for
        the wrong reason, which would understate the attack success rate. A
        red-teaming tool that under-reports is failing in the dangerous direction.
        """
        ensure_api_key()

        # One retrieval per attack, so each verdict rests on evidence for its own
        # surface.
        retrievals = [
            self.retrieve(f"{clause_text} {attack_text(attack)}") for attack in attacks
        ]

        blocks = "\n\n".join(
            f'[{index}] Attack scenario: {attack_text(attack)}\n'
            f'    Evidence retrieved for this scenario: "{evidence["passage_text"]}"'
            for index, (attack, (evidence, _passage, _matched)) in enumerate(
                zip(attacks, retrievals)
            )
        )

        failed = {"findings": [], "evidence": [], "error": True}

        prompt = BATCH_PROMPT.format(clause_text=clause_text, blocks=blocks)

        try:
            reply = generate_json(prompt, temperature=0.1)
        except Exception as error:
            logger.error("Batched auditor agent failed: %s", error)
            return failed

        verdicts = reply.get("verdicts")
        if not isinstance(verdicts, list):
            logger.error("Batched auditor reply had no verdict array: %r", reply)
            return failed

        return {
            "findings": align_verdicts(verdicts, len(attacks)),
            # One evidence block per attack, in the same order, so the verifier can
            # check each claim against the passage that claim was judged on.
            "evidence": [item[0] for item in retrievals],
            "error": False,
        }






# """Regulatory Auditor agent: evaluates policy clauses against retrieved RBI passages.

# Supports single-scenario evaluation and batched attack set judgments to optimize
# model call frequency while keeping evidence tightly scoped to each attack surface.
# """

# import json
# from pathlib import Path

# from src.agents.llm import as_bool, ensure_api_key, generate_json
# from src.retrieval import provenance, temporal
# from src.retrieval.hybrid_retriever import load_chunks_from_json, build_chroma_hybrid_retriever

# CANDIDATES_REPORTED = 3
# SNIPPET_CHARS = 220
# VERDICT_SEVERITIES = ("Low", "Medium", "High")

# FALLBACK_PASSAGE = "RBI/2023-24/53: Statutory regulatory guideline on penal charges."
# FALLBACK_ID = "RBI-REF-01"
# QUERY_CHARS = 2000


# def build_evidence(results):
#     """Convert retrieved vector results into a structured provenance evidence block."""
#     top = results[0]
#     block = provenance.from_metadata(top.metadata)
#     block["passage_text"] = top.page_content
#     block["currency"] = temporal.assess(block)
#     block["candidates"] = [
#         {
#             "citation": doc.metadata.get("citation"),
#             "document": doc.metadata.get("source"),
#             "page": doc.metadata.get("page"),
#             "passage_id": doc.metadata.get("passage_id"),
#             "section": doc.metadata.get("section"),
#             "status": doc.metadata.get("status"),
#             "snippet": doc.page_content[:SNIPPET_CHARS],
#         }
#         for doc in results[1 : CANDIDATES_REPORTED + 1]
#     ]
#     return block


# def empty_evidence():
#     """Default fallback evidence block when retrieval fails."""
#     return {
#         "citation": None,
#         "passage_id": None,
#         "section": None,
#         "passage_text": FALLBACK_PASSAGE,
#         "currency": temporal.assess({}),
#         "candidates": [],
#         "retrieval_failed": False,
#     }


# def align_verdicts(verdicts, count):
#     """Align batch model responses safely with original input attacks."""
#     aligned = [None] * count
#     for position, verdict in enumerate(verdicts):
#         if not isinstance(verdict, dict):
#             continue

#         index = verdict.get("index", position)
#         if not isinstance(index, int) or not 0 <= index < count:
#             index = position
#         if aligned[index] is not None:
#             continue

#         severity = str(verdict.get("severity") or "").strip().title()
#         aligned[index] = {
#             "violation_confirmed": as_bool(verdict.get("violation_confirmed", False)),
#             "severity": severity if severity in VERDICT_SEVERITIES else "Medium",
#             "explanation": str(verdict.get("explanation") or "").strip(),
#         }
#     return aligned


# def attack_text(attack):
#     """Extract standard scenario text from an attack object."""
#     return attack.get("attack_scenario") or attack.get("title") or "Exploit regulatory loophole."


# SINGLE_PROMPT = """
#     You are the Regulatory Auditor Agent for Reguard AI, an enterprise RBI compliance engine.
#     Analyze the given loan policy clause and adversarial attack scenario against the retrieved RBI statutory evidence.

#     Policy Clause:
#     "{clause_text}"

#     Adversarial Attack Scenario / Loophole:
#     {attack_scenario}

#     Retrieved RBI Statutory Evidence:
#     "{passage}"

#     Task:
#     1. Determine if the policy clause combined with the attack scenario violates RBI guidelines.
#     2. Provide a clear regulatory explanation and severity level (Low, Medium, High).

#     Return your response strictly as a valid JSON object with these exact keys:
#     - "violation_confirmed": boolean (true if violation exists, false otherwise)
#     - "severity": string ("Low", "Medium", "High")
#     - "explanation": string (detailed regulatory reasoning)
#     - "matched_rbi_passage_id": string ("{matched_id}")
#     - "retrieved_passage": string (the exact retrieved RBI statutory evidence text provided above)

#     Do not include markdown code block wrappers in your response, just raw JSON.
#     """

# BATCH_PROMPT = """
#     You are the Regulatory Auditor Agent for Reguard AI, an enterprise RBI compliance engine.
#     You are judging one loan policy clause against several independent attack
#     scenarios. Each scenario comes with the RBI evidence retrieved for it. Judge
#     every scenario only against its own evidence, and on its own.

#     Policy Clause:
#     "{clause_text}"

#     Attack Scenarios:
#     {blocks}

#     Task:
#     For every scenario, decide whether the clause combined with that scenario
#     violates RBI guidelines, and give a severity level (Low, Medium, High).

#     Return your response strictly as a valid JSON object with one key "verdicts",
#     whose value is an array holding exactly one entry per scenario, in the order
#     given. Each entry must have these exact keys:
#     - "index": integer, the index shown for that scenario
#     - "violation_confirmed": boolean
#     - "severity": string ("Low", "Medium", "High")
#     - "explanation": string (detailed regulatory reasoning)

#     Do not include markdown code block wrappers in your response, just raw JSON.
#     """


# class RegulatoryAuditor:
#     """Audits policy clauses against hybrid RAG retrieved RBI guidelines."""

#     def __init__(self):
#         try:
#             docs = load_chunks_from_json()
#             self.retriever = build_chroma_hybrid_retriever(docs)
#         except Exception:
#             print("Warning: Retriever unavailable; auditor will default to fallback passage.")
#             self.retriever = None

#     def retrieve(self, query: str):
#         """Retrieve regulatory evidence locally without triggering model calls."""
#         evidence = empty_evidence()
#         passage_text = FALLBACK_PASSAGE
#         matched_id = FALLBACK_ID

#         if not self.retriever:
#             return evidence, passage_text, matched_id

#         try:
#             results = self.retriever.invoke(query[:QUERY_CHARS])
#             if results:
#                 evidence = build_evidence(results)
#                 passage_text = evidence["passage_text"]
#                 matched_id = results[0].metadata.get("source", FALLBACK_ID)
#         except Exception as error:
#             print(f"Error: RAG retrieval failed in auditor: {error}")
#             evidence["retrieval_failed"] = True
#             evidence["retrieval_error"] = str(error)
#             evidence["currency"] = temporal.assess({})

#         return evidence, passage_text, matched_id

#     def audit_clause(self, clause_text: str, attack_scenario: dict) -> dict:
#         ensure_api_key()

#         query = f"{clause_text} {attack_scenario.get('attack_scenario', '')}"
#         evidence, retrieved_passage_text, matched_id = self.retrieve(query)

#         prompt = SINGLE_PROMPT.format(
#             clause_text=clause_text,
#             attack_scenario=json.dumps(attack_scenario, indent=2),
#             passage=retrieved_passage_text,
#             matched_id=matched_id,
#         )

#         try:
#             result = generate_json(prompt, temperature=0.1)
#         except Exception as error:
#             print(f"Error: Auditor agent failed: {error}")
#             return {
#                 "violation_confirmed": False,
#                 "severity": "Low",
#                 "explanation": f"Audit analysis failed due to error: {str(error)}",
#                 "matched_rbi_passage_id": matched_id,
#                 "retrieved_passage": retrieved_passage_text,
#                 "evidence": evidence,
#                 "error": True,
#             }

#         result["retrieved_passage"] = retrieved_passage_text
#         result["matched_rbi_passage_id"] = matched_id
#         result["evidence"] = evidence
#         result["error"] = False
#         return result

#     def audit_clause_batch(self, clause_text: str, attacks: list) -> dict:
#         """Evaluate a complete attack set against a single clause in one call."""
#         ensure_api_key()

#         retrievals = [
#             self.retrieve(f"{clause_text} {attack_text(attack)}") for attack in attacks
#         ]

#         blocks = "\n\n".join(
#             f'[{index}] Attack scenario: {attack_text(attack)}\n'
#             f'    Evidence retrieved: "{evidence["passage_text"]}"'
#             for index, (attack, (evidence, _passage, _matched)) in enumerate(
#                 zip(attacks, retrievals)
#             )
#         )

#         failed = {"findings": [], "evidence": [], "error": True}
#         prompt = BATCH_PROMPT.format(clause_text=clause_text, blocks=blocks)

#         try:
#             reply = generate_json(prompt, temperature=0.1)
#         except Exception as error:
#             print(f"Error: Batched auditor agent failed: {error}")
#             return failed

#         verdicts = reply.get("verdicts")
#         if not isinstance(verdicts, list):
#             print(f"Error: Batched auditor reply missing verdict array: {reply}")
#             return failed

#         return {
#             "findings": align_verdicts(verdicts, len(attacks)),
#             "evidence": [item[0] for item in retrievals],
#             "error": False,
#         }