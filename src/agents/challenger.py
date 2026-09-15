import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv
load_dotenv()


def generate_adversarial_attack(structured_clause: dict) -> dict:
    """
    Red-Team Challenger Agent. Takes a structured clause and simulates an 
    adversarial audit to find compliance loopholes or RBI guideline violations.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY environment variable is not set. Please configure it.")

    client = genai.Client()

    prompt = f"""
    You are the Challenger (Red-Team) Agent for Reguard AI. 
    Your objective is to stress-test enterprise digital lending policies by finding regulatory weaknesses, 
    loopholes, or potential RBI guideline violations based on the following structured clause.

    Structured Policy Clause:
    {json.dumps(structured_clause, indent=2)}

    Think like an aggressive fintech regulatory auditor or security red-teamer. Look for:
    - Excessive penal charges or hidden fees.
    - Lack of explicit borrower disclosure/consent windows.
    - Unfair terms or regulatory non-compliance.

    Return your analysis strictly as a valid JSON object with these exact keys:
    - "vulnerability_detected": true or false
    - "explanation": A clear explanation of why this policy clause is non-compliant or risky
    - "severity": "High", "Medium", or "Low"
    - "attack_scenario": A realistic borrower situation that exposes this loophole

    Do not include markdown code block wrappers (like ```json) in your response if possible, just raw JSON.
    """

    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.6,  # Higher temperature gives creative red-team scenarios
            ),
        )

        # Clean markdown code blocks if the model includes them
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        return json.loads(raw_text)

    except json.JSONDecodeError as jde:
        print(f"[Warning] Failed to parse JSON attack report: {jde}")
        print(f"Raw response was: {response.text}")
        return {
            "vulnerability_detected": False,
            "explanation": "Failed to parse model response as JSON.",
            "severity": "Low",
            "attack_scenario": ""
        }
        
    except Exception as e:
        print(f"[Error] Encountered an issue during Challenger agent execution: {e}")
        return {}

if __name__ == "__main__":
    print("--- Running Red-Team Challenger Agent (challenger.py) ---")
    
    # Sample structured input (mimicking what analyst.py produces)
    sample_input = {
        "actor": "Lender",
        "action": "levy penal charge",
        "limit": "2% per month",
        "condition": "delayed repayment after 7 days"
    }
    
    print(f"\nTargeting Clause Structure:\n{json.dumps(sample_input, indent=4)}")
    print("\nLaunching adversarial red-team simulation via Gemini...")
    
    attack_report = generate_adversarial_attack(sample_input)
    
    print("\nGenerated Vulnerability Report:")
    print(json.dumps(attack_report, indent=4))