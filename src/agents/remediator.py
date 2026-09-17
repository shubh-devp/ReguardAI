import json
import logging

from src.agents.llm import ensure_api_key, generate_json

logger = logging.getLogger(__name__)


def remediate_clause(clause_text: str, audit_finding: dict) -> dict:
    """
    Remediator Agent. Drafts an RBI-compliant rewrite for a flagged policy clause.
    Does NOT generate ASR numbers; all ASR metrics are calculated programmatically 
    by the deterministic Re-Test Agent.
    """
    ensure_api_key()

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
        result = generate_json(prompt, temperature=0.2)

        # ASR is filled in deterministically by the Re-Test Agent, never by the model.
        result["asr_before"] = 0.0
        result["asr_after"] = 0.0
        return result

    except Exception as error:
        logger.error("Remediator agent failed: %s", error)
        return {
            "patched_clause_text": clause_text,
            "remediation_rationale": f"Remediation drafting failed due to error: {str(error)}",
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





# """Remediator agent: drafts RBI-compliant rewrites for flagged policy clauses."""

# import json

# from src.agents.llm import ensure_api_key, generate_json


# def remediate_clause(clause_text: str, audit_finding: dict) -> dict:
#     """Draft an RBI-compliant rewrite for a flagged policy clause.

#     Note: Does NOT generate ASR numbers; all ASR metrics are calculated programmatically
#     by the deterministic Re-Test Agent.
#     """
#     ensure_api_key()

#     prompt = f"""
#     You are the Remediator Agent for Reguard AI, an enterprise RBI compliance engine.
#     Your task is to rewrite a non-compliant loan policy clause so that it fully adheres to Reserve Bank of India (RBI) regulations.

#     Original Clause:
#     "{clause_text}"

#     Auditor Finding / Violation Rationale:
#     {json.dumps(audit_finding, indent=2)}

#     Task:
#     1. Draft a legally sound, compliant replacement clause that eliminates the regulatory violation while preserving the lender's operational intent where possible.
#     2. Provide a clear remediation rationale referencing standard regulatory principles (e.g., Fair Practice Code, Key Fact Statement disclosures).

#     Return your response strictly as a valid JSON object with these exact keys:
#     - "patched_clause_text": string (the revised compliant clause text)
#     - "remediation_rationale": string (explanation of why this revision satisfies RBI guidelines)
#     - "status": string ("Resolved")

#     Do not include markdown code block wrappers (like ```json) in your response, just raw JSON.
#     """

#     try:
#         result = generate_json(prompt, temperature=0.2)

#         # ASR metrics are handled deterministically downstream by the Re-Test Agent
#         result["asr_before"] = 0.0
#         result["asr_after"] = 0.0
#         return result

#     except Exception as error:
#         print(f"Error: Remediator agent failed: {error}")
#         return {
#             "patched_clause_text": clause_text,
#             "remediation_rationale": f"Remediation drafting failed due to error: {str(error)}",
#             "status": "Failed",
#             "asr_before": 0.0,
#             "asr_after": 0.0
#         }


# if __name__ == "__main__":
#     print("--- Running Remediator Agent (remediator.py) ---")
#     sample_clause = "The lender shall levy a penal charge of 2% per month on delayed repayments."
#     sample_audit = {
#         "violation_confirmed": True,
#         "explanation": "Monthly recurring penal charges violate RBI guidelines against compounding penal interest."
#     }
#     print(json.dumps(remediate_clause(sample_clause, sample_audit), indent=4))