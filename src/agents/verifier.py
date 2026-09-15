import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv
load_dotenv()

def verify_evidence(clause_text: str, audit_finding: dict, retrieved_passage: str) -> dict:
    """
    Evidence Verifier Agent. Cross-references the auditor's violation claim and clause text 
    against the actual retrieved RBI legal passage to prevent citation hallucination.
    Fails closed (is_supported = False) on any exception or parsing error.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY environment variable is not set. Please configure it.")

    client = genai.Client()

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
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,  # Low temperature for strict factual checking
            ),
        )

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        return json.loads(raw_text)

    except Exception as e:
        print(f"[Error] Failed during evidence verification: {e}")
        # SECURITY FIX: Fail closed on errors to prevent unverified passages from slipping through
        return {
            "is_supported": False,
            "verification_rationale": f"Verification failed closed due to error/parsing failure: {str(e)}",
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