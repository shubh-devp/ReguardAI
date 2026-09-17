"""Evidence Verifier agent: does the retrieved passage actually support the claim?

Two entry points, one check:

- ``verify_evidence`` checks a single claim.
- ``verify_evidence_batch`` checks several claims against the same passage in one call.

Both fail closed: any exception, parsing failure, or claim the model does not answer
comes back as unsupported. The distinction between "verified as unsupported" and
"could not be checked" is carried in the ``error`` flag, because a caller that is
measuring attack success has to tell those apart - a failed call is not evidence
that the claim was wrong.
"""

import json
import logging

from src.agents.llm import align_by_index, as_bool, ensure_api_key, generate_json

logger = logging.getLogger(__name__)

# One claim's explanation is a paragraph; the cap stops a long finding from turning
# a batched verification into a huge request.
CLAIM_CHARS = 600

SINGLE_PROMPT = """
    You are the Evidence Verifier Agent for Reguard AI.
    Your task is to verify whether the retrieved RBI legal snippet actually and logically supports 
    the auditor's compliance violation claim for the given policy clause.

    Policy Clause:
    "{clause_text}"

    Auditor Finding / Claim:
    {claim}

    Retrieved RBI Legal Snippet (Evidence):
    "{passage}"

    Task:
    1. Check if the retrieved legal snippet explicitly addresses or supports the specific violation claimed.
    2. Determine if this is a valid citation or a hallucinated/irrelevant match.

    Return your response strictly as a valid JSON object with these exact keys:
    - "is_supported": boolean (true if the evidence supports the claim, false otherwise)
    - "verification_rationale": brief explanation of why the evidence matches or fails
    - "confidence_score": float between 0.0 and 1.0 indicating confidence in the citation validity

    Do not include markdown code block wrappers (like ```json) in your response, just raw JSON.
    """

BATCH_PROMPT = """
    You are the Evidence Verifier Agent for Reguard AI.
    You are given several violation claims that were each made against the same
    policy clause, and the RBI evidence that was retrieved for each claim. Check
    every claim against its own evidence, and on its own - a verdict on one claim
    must not influence another.

    Policy Clause:
    "{clause_text}"

    Claims, each with its own retrieved evidence and the index you must report it
    under:

    {blocks}

    Task:
    For every claim, decide whether the evidence shown for that claim explicitly
    addresses and supports that specific violation, or whether it is a hallucinated
    or irrelevant match.

    Return your response strictly as a valid JSON object with one key "verdicts",
    whose value is an array holding exactly one entry per claim, in the order given.
    Each entry must have these exact keys:
    - "index": integer, the index shown for that claim
    - "is_supported": boolean
    - "verification_rationale": brief explanation of why the evidence matches or fails
    - "confidence_score": float between 0.0 and 1.0

    Do not include markdown code block wrappers (like ```json) in your response, just raw JSON.
    """


def _unsupported(rationale):
    return {"is_supported": False, "verification_rationale": rationale, "confidence_score": 0.0}


def aligned_verifications(verdicts, count):
    """Coerce a batched verifier reply into a fixed shape, in claim order.

    A claim the model did not answer stays ``None`` rather than defaulting to
    unsupported, so the caller can tell "the model said no" from "the model never
    replied about this one".
    """
    aligned = []
    for verdict in align_by_index(verdicts, count):
        if verdict is None:
            aligned.append(None)
            continue

        confidence = verdict.get("confidence_score")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            confidence = 0.0

        aligned.append(
            {
                "is_supported": as_bool(verdict.get("is_supported", False)),
                "verification_rationale": str(verdict.get("verification_rationale") or "").strip(),
                "confidence_score": float(confidence),
            }
        )
    return aligned


def verify_evidence(clause_text: str, audit_finding: dict, retrieved_passage: str) -> dict:
    """
    Evidence Verifier Agent. Cross-references the auditor's violation claim and clause text 
    against the actual retrieved RBI legal passage to prevent citation hallucination.
    Fails closed (is_supported = False) on any exception or parsing error.
    """
    ensure_api_key()

    prompt = SINGLE_PROMPT.format(
        clause_text=clause_text,
        claim=json.dumps(audit_finding, indent=2),
        passage=retrieved_passage,
    )

    try:
        # Low temperature, because this step is a strict factual check.
        return generate_json(prompt, temperature=0.1)

    except Exception as error:
        logger.error("Evidence verifier failed: %s", error)
        # Fail closed, so an unverified passage can never be treated as supported.
        # The error flag lets a caller tell "verified as unsupported" apart from
        # "could not be checked", which matters when a failure would otherwise be
        # read as evidence that a patch worked.
        return {
            **_unsupported(f"Verification failed closed due to error/parsing failure: {str(error)}"),
            "error": True,
        }


def verify_evidence_batch(clause_text: str, claims: list, passages: list) -> dict:
    """Check the citation behind each claim against that claim's own passage.

    ``passages`` is aligned with ``claims``: entry ``i`` is the evidence claim ``i``
    was judged on. One model call covers the whole set.

    Returns ``{"verdicts": [...]}`` aligned with ``claims``, or ``{"error": True}``
    when nothing could be checked, in which case every claim is left unmeasured.
    """
    ensure_api_key()

    if len(passages) != len(claims):
        # Claims and evidence come from the same batch, so a mismatch means
        # something upstream is wrong. Verifying against the wrong passage would be
        # worse than not verifying, so this fails closed.
        logger.error(
            "Claim/evidence count mismatch: %d claims, %d passages", len(claims), len(passages)
        )
        return {"verdicts": [None] * len(claims), "error": True}

    blocks = "\n\n".join(
        f"[{index}] Claim: {json.dumps(claim, default=str)[:CLAIM_CHARS]}\n"
        f'    Evidence retrieved for this claim: "{passage}"'
        for index, (claim, passage) in enumerate(zip(claims, passages))
    )

    prompt = BATCH_PROMPT.format(clause_text=clause_text, blocks=blocks)

    try:
        reply = generate_json(prompt, temperature=0.1)
    except Exception as error:
        logger.error("Batched evidence verifier failed: %s", error)
        return {"verdicts": [None] * len(claims), "error": True}

    verdicts = reply.get("verdicts")
    if not isinstance(verdicts, list):
        logger.error("Batched verifier reply had no verdict array: %r", reply)
        return {"verdicts": [None] * len(claims), "error": True}

    return {"verdicts": aligned_verifications(verdicts, len(claims)), "error": False}






# """Evidence Verifier agent: cross-references auditor claims against retrieved RBI passages."""

# import json

# from src.agents.llm import align_by_index, as_bool, ensure_api_key, generate_json

# CLAIM_CHARS = 600

# SINGLE_PROMPT = """
#     You are the Evidence Verifier Agent for Reguard AI.
#     Your task is to verify whether the retrieved RBI legal snippet actually and logically supports 
#     the auditor's compliance violation claim for the given policy clause.

#     Policy Clause:
#     "{clause_text}"

#     Auditor Finding / Claim:
#     {claim}

#     Retrieved RBI Legal Snippet (Evidence):
#     "{passage}"

#     Task:
#     1. Check if the retrieved legal snippet explicitly addresses or supports the specific violation claimed.
#     2. Determine if this is a valid citation or a hallucinated/irrelevant match.

#     Return your response strictly as a valid JSON object with these exact keys:
#     - "is_supported": boolean (true if the evidence supports the claim, false otherwise)
#     - "verification_rationale": brief explanation of why the evidence matches or fails
#     - "confidence_score": float between 0.0 and 1.0 indicating confidence in the citation validity

#     Do not include markdown code block wrappers in your response, just raw JSON.
#     """

# BATCH_PROMPT = """
#     You are the Evidence Verifier Agent for Reguard AI.
#     You are given several violation claims that were each made against the same
#     policy clause, and the RBI evidence that was retrieved for each claim. Check
#     every claim against its own evidence, and on its own.

#     Policy Clause:
#     "{clause_text}"

#     Claims with retrieved evidence:
#     {blocks}

#     Task:
#     For every claim, decide whether the evidence shown for that claim explicitly
#     addresses and supports that specific violation, or whether it is a hallucinated
#     or irrelevant match.

#     Return your response strictly as a valid JSON object with one key "verdicts",
#     whose value is an array holding exactly one entry per claim, in the order given.
#     Each entry must have these exact keys:
#     - "index": integer, the index shown for that claim
#     - "is_supported": boolean
#     - "verification_rationale": brief explanation of why the evidence matches or fails
#     - "confidence_score": float between 0.0 and 1.0

#     Do not include markdown code block wrappers in your response, just raw JSON.
#     """


# def _unsupported(rationale):
#     return {"is_supported": False, "verification_rationale": rationale, "confidence_score": 0.0}


# def aligned_verifications(verdicts, count):
#     """Coerce batch verifier replies into a fixed shape aligned with claim order."""
#     aligned = []
#     for verdict in align_by_index(verdicts, count):
#         if verdict is None:
#             aligned.append(None)
#             continue

#         confidence = verdict.get("confidence_score")
#         if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
#             confidence = 0.0

#         aligned.append(
#             {
#                 "is_supported": as_bool(verdict.get("is_supported", False)),
#                 "verification_rationale": str(verdict.get("verification_rationale") or "").strip(),
#                 "confidence_score": float(confidence),
#             }
#         )
#     return aligned


# def verify_evidence(clause_text: str, audit_finding: dict, retrieved_passage: str) -> dict:
#     """Verify single audit claim against retrieved legal evidence (fails closed)."""
#     ensure_api_key()

#     prompt = SINGLE_PROMPT.format(
#         clause_text=clause_text,
#         claim=json.dumps(audit_finding, indent=2),
#         passage=retrieved_passage,
#     )

#     try:
#         # Low temperature for strict factual consistency checks
#         return generate_json(prompt, temperature=0.1)
#     except Exception as error:
#         print(f"Error: Evidence verifier failed: {error}")
#         return {
#             **_unsupported(f"Verification failed closed due to error/parsing failure: {str(error)}"),
#             "error": True,
#         }


# def verify_evidence_batch(clause_text: str, claims: list, passages: list) -> dict:
#     """Verify multiple citations against individual claim passages in one call."""
#     ensure_api_key()

#     if len(passages) != len(claims):
#         print(f"Error: Claim/evidence count mismatch: {len(claims)} claims, {len(passages)} passages.")
#         return {"verdicts": [None] * len(claims), "error": True}

#     blocks = "\n\n".join(
#         f"[{index}] Claim: {json.dumps(claim, default=str)[:CLAIM_CHARS]}\n"
#         f'    Evidence retrieved: "{passage}"'
#         for index, (claim, passage) in enumerate(zip(claims, passages))
#     )

#     prompt = BATCH_PROMPT.format(clause_text=clause_text, blocks=blocks)

#     try:
#         reply = generate_json(prompt, temperature=0.1)
#     except Exception as error:
#         print(f"Error: Batched evidence verifier failed: {error}")
#         return {"verdicts": [None] * len(claims), "error": True}

#     verdicts = reply.get("verdicts")
#     if not isinstance(verdicts, list):
#         print(f"Error: Batched verifier reply missing verdict array: {reply}")
#         return {"verdicts": [None] * len(claims), "error": True}

#     return {"verdicts": aligned_verifications(verdicts, len(claims)), "error": False}