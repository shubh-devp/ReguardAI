import json
import logging

from src.agents.llm import ensure_api_key, generate_json

logger = logging.getLogger(__name__)


def generate_adversarial_attack(structured_clause: dict) -> dict:
    """
    Red-Team Challenger Agent. Takes a structured clause and simulates an 
    adversarial audit to find compliance loopholes or RBI guideline violations.
    """
    ensure_api_key()

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
        # A higher temperature gives the challenger room for creative attack scenarios.
        return generate_json(prompt, temperature=0.6)

    except Exception as error:
        logger.error("Challenger agent failed: %s", error)
        return {
            "vulnerability_detected": False,
            "explanation": "Failed to parse model response as JSON.",
            "severity": "Low",
            "attack_scenario": ""
        }

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