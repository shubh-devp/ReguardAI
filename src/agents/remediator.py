import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv
load_dotenv()

def remediate_clause(clause_text: str, audit_finding: dict) -> dict:
    """
    Remediator Agent. Drafts an RBI-compliant rewrite for a flagged policy clause.
    Does NOT generate ASR numbers; all ASR metrics are calculated programmatically 
    by the deterministic Re-Test Agent.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY environment variable is not set. Please configure it.")

    client = genai.Client()

    prompt = f"""
    You are the Remediator Agent for Reguard AI, an enterprise RBI compliance engine.
    Your task is to rewrite a non-compliant loan policy clause so that it fully adheres to Reserve Bank of India (RBI) regulations.

    Original Clause:
    "{clause_text}"

    Auditor Finding / Violation Rationale:
    {json.dumps(audit_finding, indent=2)}

    Task:
    1. Draft a legally sound, compliant replacement clause that eliminates the regulatory violation while preserving the lender's operational intent where possible.
    2. Provide a clear remediation rationale referencing standard regulatory principles (e.g., Fair Practice Code, Key Fact Statement disclosures).

    Return your response strictly as a valid JSON object with these exact keys:
    - "patched_clause_text": string (the revised compliant clause text)
    - "remediation_rationale": string (explanation of why this revision satisfies RBI guidelines)
    - "status": string ("Resolved")

    Do not include markdown code block wrappers (like ```json) in your response, just raw JSON.
    """

    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
            ),
        )

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        result = json.loads(raw_text)
        
        # Ensure fallback placeholders for ASR (to be overwritten deterministically by ReTestAgent)
        result["asr_before"] = 0.0
        result["asr_after"] = 0.0
        return result

    except Exception as e:
        print(f"[Error] Failed during remediation drafting: {e}")
        return {
            "patched_clause_text": clause_text,
            "remediation_rationale": f"Remediation drafting failed due to error: {str(e)}",
            "status": "Failed",
            "asr_before": 0.0,
            "asr_after": 0.0
        }

if __name__ == "__main__":
    print("--- Running Remediator Agent (remediator.py) ---")
    sample_clause = "The lender shall levy a penal charge of 2% per month on delayed repayments."
    sample_audit = {
        "violation_confirmed": True,
        "explanation": "Monthly recurring penal charges violate RBI guidelines against compounding penal interest."
    }
    print(json.dumps(remediate_clause(sample_clause, sample_audit), indent=4))