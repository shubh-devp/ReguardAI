import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field



class PolicyStructure(BaseModel):
    actor: str = Field(description="Who is responsible or taking the action (e.g., Lender, Borrower, System)")
    action: str = Field(description="The operational activity being performed (e.g., levy penal charge, disburse loan)")
    limit: str = Field(description="Numerical thresholds, interest rates, caps, or time limits (e.g., 2% per month, 7 days)")
    condition: str = Field(description="The triggers or constraints under which this applies (e.g., if dues are delayed)")


def extract_policy_structure(policy_text: str) -> dict:
    #Parses an enterprise digital lending policy clause into a structured 
    #JSON schema (actor, action, limit, condition) using the Gemini API[cite: 1].

    if not os.environ.get("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY environment variable is not set. Please configure it.")

    client = genai.Client()

    prompt = f"""
    You are a compliance analyst specializing in fintech and digital lending regulations.
    Analyze the following enterprise policy clause and break it down into a structured JSON format.

    Policy Clause:
    "{policy_text}"
    """

    try:
        response = client.models.generate_content(
            model= 'gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,  # Keep it deterministic and precise for legal analysis
                response_mime_type="application/json",
                response_schema=PolicyStructure,  # Guarantees schema adherence natively
            ),
        )

        raw_text = response.text

        return json.loads(raw_text)



    except Exception as e:
        print(f"[Error] Encountered an issue during Gemini API execution: {e}")
        return {}


if __name__ == "__main__":
    print("--- Running Policy Analyst Agent (analyst.py) ---")
    
    # Sample real-world lending policy clause to test against
    sample_clause = (
        "The lender shall levy a penal charge of 2% per month on delayed repayments "
        "if the borrower fails to clear dues within 7 days of the billing cycle end."
    )
    
    print(f"\nAnalyzing Policy Text:\n\"{sample_clause}\"\n")
    print("Sending request to Gemini model with native Pydantic validation...")
    
    structured_data = extract_policy_structure(sample_clause)
    
    print("\nParsed Structural Breakdown:")
    print(json.dumps(structured_data, indent=4))