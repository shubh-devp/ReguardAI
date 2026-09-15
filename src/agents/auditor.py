import json
import logging

from src.agents.llm import ensure_api_key, generate_json
from src.retrieval import provenance
from src.retrieval.hybrid_retriever import load_chunks_from_json, build_chroma_hybrid_retriever

logger = logging.getLogger(__name__)

# How many retrieved candidates to report alongside the passage actually cited.
CANDIDATES_REPORTED = 3
SNIPPET_CHARS = 220


def build_evidence(results):
    """Turn the retrieved chunks into a provenance block.

    A finding is only worth as much as the evidence behind it, so this records
    which document, page, section and passage id the decision rested on, plus the
    runner-up candidates that were considered.
    """
    top = results[0]
    block = provenance.from_metadata(top.metadata)
    block["passage_text"] = top.page_content
    block["candidates"] = [
        {
            "citation": document.metadata.get("citation"),
            "document": document.metadata.get("source"),
            "page": document.metadata.get("page"),
            "passage_id": document.metadata.get("passage_id"),
            "section": document.metadata.get("section"),
            "status": document.metadata.get("status"),
            "snippet": document.page_content[:SNIPPET_CHARS],
        }
        for document in results[:CANDIDATES_REPORTED]
    ]
    return block


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
            #Falling back to a fixed passage is the safe behaviour, but it is
            #also silent evidence loss, so make the reason visible in the log.
            logger.exception("Retriever unavailable; audits will use a fixed passage")
            self.retriever = None

    def audit_clause(self, clause_text: str, attack_scenario: dict) -> dict:
        ensure_api_key()

        # 1. Retrieve statutory evidence locally
        retrieved_passage_text = "RBI/2023-24/53: Statutory regulatory guideline on penal charges."
        matched_id = "RBI-REF-01"
        evidence = {
            "citation": None,
            "passage_id": None,
            "section": None,
            "passage_text": retrieved_passage_text,
            "candidates": [],
            "retrieval_failed": False,
        }

        if self.retriever:
            try:
                query = f"{clause_text} {attack_scenario.get('attack_scenario', '')}"
                results = self.retriever.invoke(query)
                if results:
                    evidence = build_evidence(results)
                    retrieved_passage_text = evidence["passage_text"]
                    # Kept as the filename for backwards compatibility with the
                    # existing audit trail; the precise citation is in `evidence`.
                    matched_id = results[0].metadata.get("source", "RBI-REF-01")
            except Exception as error:
                logger.exception("RAG retrieval failed in the auditor")
                evidence["retrieval_failed"] = True
                evidence["retrieval_error"] = str(error)

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
                "retrieved_passage": retrieved_passage_text,
                "evidence": evidence,
            }

        # The retrieved text is authoritative, so it is not taken from the model.
        result["retrieved_passage"] = retrieved_passage_text
        result["matched_rbi_passage_id"] = matched_id
        result["evidence"] = evidence
        return result