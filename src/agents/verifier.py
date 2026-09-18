import json
import logging

from src.agents.llm import align_by_index, as_bool, ensure_api_key, generate_json

logger = logging.getLogger(__name__)

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
        return {
            **_unsupported(f"Verification failed closed due to error/parsing failure: {str(error)}"),
            "error": True,
        }


def verify_evidence_batch(clause_text: str, claims: list, passages: list) -> dict:
    ensure_api_key()

    if len(passages) != len(claims):
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
