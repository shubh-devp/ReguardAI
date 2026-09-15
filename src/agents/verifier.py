import json
import logging

from src.agents.llm import ensure_api_key, generate_json

logger = logging.getLogger(__name__)


def verify_evidence(clause_text: str, audit_finding: dict, retrieved_passage: str) -> dict:
    """
    Evidence Verifier Agent. Cross-references the auditor's violation claim and clause text 
    against the actual retrieved RBI legal passage to prevent citation hallucination.
    Fails closed (is_supported = False) on any exception or parsing error.
    """
    ensure_api_key()

    prompt = f"""
    You are the Evidence Verifier Agent for Reguard AI.
    Your task is to verify whether the retrieved RBI legal snippet actually and logically supports 
    the auditor's compliance violation claim for the given policy clause.

    Policy Clause:
    "{clause_text}"

    Auditor Finding / Claim:
    {json.dumps(audit_finding, indent=2)}

    Retrieved RBI Legal Snippet (Evidence):
    "{retrieved_passage}"

    Task:
    1. Check if the retrieved legal snippet explicitly addresses or supports the specific violation claimed.
    2. Determine if this is a valid citation or a hallucinated/irrelevant match.

    Return your response strictly as a valid JSON object with these exact keys:
    - "is_supported": boolean (true if the evidence supports the claim, false otherwise)
    - "verification_rationale": brief explanation of why the evidence matches or fails
    - "confidence_score": float between 0.0 and 1.0 indicating confidence in the citation validity

    Do not include markdown code block wrappers (like ```json) in your response, just raw JSON.
    """

    try:
        # Low temperature, because this step is a strict factual check.
        return generate_json(prompt, temperature=0.1)

    except Exception as error:
        logger.error("Evidence verifier failed: %s", error)
        # Fail closed, so an unverified passage can never be treated as supported.
        return {
            "is_supported": False,
            "verification_rationale": f"Verification failed closed due to error/parsing failure: {str(error)}",
            "confidence_score": 0.0
        }

if __name__ == "__main__":
    print("--- Running Evidence Verifier Agent (verifier.py) ---")
    
    sample_clause = "The lender shall levy a penal charge of 2% per month on delayed repayments."
    sample_audit = {
        "violation_confirmed": True,
        "explanation": "Monthly recurring penal charges violate RBI guidelines against compounding penal interest."
    }
    sample_passage = "RBI/2023-24/53: Penal charges, if any, levied for non-compliance of material terms and conditions by the borrower shall not be capitalized, i.e., no further interest computed on such charges."

    res = verify_evidence(sample_clause, sample_audit, sample_passage)
    print(json.dumps(res, indent=4))