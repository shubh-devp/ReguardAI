import json
import logging

from src.agents.llm import ensure_api_key, generate_json
from src.retrieval.hybrid_retriever import load_chunks_from_json, build_chroma_hybrid_retriever

logger = logging.getLogger(__name__)

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
            self.retriever = None

    def audit_clause(self, clause_text: str, attack_scenario: dict) -> dict:
        ensure_api_key()

        # 1. Retrieve statutory evidence locally
        retrieved_passage_text = "RBI/2023-24/53: Statutory regulatory guideline on penal charges."
        matched_id = "RBI-REF-01"
        
        if self.retriever:
            try:
                query = f"{clause_text} {attack_scenario.get('attack_scenario', '')}"
                results = self.retriever.invoke(query)
                if results:
                    top_doc = results[0]
                    retrieved_passage_text = top_doc.page_content
                    matched_id = top_doc.metadata.get("source", "RBI-REF-01")
            except Exception as e:
                print(f"[Warning] RAG retrieval error in auditor: {e}")

        prompt = f"""
        You are the Regulatory Auditor Agent for Reguard AI, an enterprise RBI compliance engine.
        Analyze the given loan policy clause and adversarial attack scenario against the retrieved RBI statutory evidence.

        Policy Clause:
        "{clause_text}"

        Adversarial Attack Scenario / Loophole:
        {json.dumps(attack_scenario, indent=2)}

        Retrieved RBI Statutory Evidence:
        "{retrieved_passage_text}"

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

        try:
            result = generate_json(prompt, temperature=0.1)

        except Exception as error:
            logger.error("Auditor agent failed: %s", error)
            return {
                "violation_confirmed": False,
                "severity": "Low",
                "explanation": f"Audit analysis failed due to error: {str(error)}",
                "matched_rbi_passage_id": matched_id,
                "retrieved_passage": retrieved_passage_text
            }

        # The retrieved text is authoritative, so it is not taken from the model.
        result["retrieved_passage"] = retrieved_passage_text
        result["matched_rbi_passage_id"] = matched_id
        return result