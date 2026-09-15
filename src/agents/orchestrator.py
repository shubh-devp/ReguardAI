import json
import logging

from src.models.risk_classifier import PolicyRiskClassifier
from src.agents.challenger import generate_adversarial_attack
from src.agents.auditor import RegulatoryAuditor
from src.agents.verifier import verify_evidence
from src.agents.remediator import remediate_clause
from src.agents.retest import ReTestAgent
from src.agents.llm import as_bool
from src.database.sql_manager import (
    init_db,
    insert_policy,
    insert_clause,
    insert_audit_finding,
    insert_remediation_result
)

logger = logging.getLogger(__name__)


class ReguardOrchestrator:
    def __init__(self):
        init_db()
        self.classifier = PolicyRiskClassifier()
        self.auditor = RegulatoryAuditor()
        self.retest_agent = ReTestAgent()

    def run(self, policy_name: str, full_text: str, clause_text: str) -> dict:
        policy_id = insert_policy(policy_name, full_text)
        
        # ML / NLP Risk Triage
        risk = self.classifier.predict_risk(clause_text)
        clause_id = insert_clause(
            policy_id=policy_id,
            clause_text=clause_text,
            actor="Lender",
            action="Clause Execution",
            limit_val="N/A",
            condition="Default",
            risk_score=risk["risk_score"]
        )

        if not risk["requires_red_teaming"]:
            return {"status": "compliant", "policy_id": policy_id, "clause_id": clause_id, "risk": risk}

        # Challenger Agent
        dummy_clause = {"actor": "Lender", "action": clause_text, "limit": "As specified", "condition": "Default"}
        attack = generate_adversarial_attack(dummy_clause)
        
        # Hybrid RAG & Auditor Agent
        audit = self.auditor.audit_clause(clause_text, attack)
        retrieved_passage = audit.get("retrieved_passage") or audit.get("explanation", "RBI regulatory context.")

        # Evidence Verifier Agent (Fail-Closed: default to False)
        verification = verify_evidence(clause_text, audit, retrieved_passage)
        is_supported = as_bool(verification.get("is_supported", False))
        confidence = verification.get("confidence_score")
        evidence = audit.get("evidence") or {}

        if isinstance(confidence, (int, float)) and confidence < 0.5:
            # A low-confidence verification is not strong enough to justify an
            # automatic rewrite, so it is reported rather than acted on.
            logger.warning(
                "Verifier confidence %.2f is below the 0.5 threshold for clause %r",
                confidence, clause_text[:60],
            )

        finding_id = insert_audit_finding(
            policy_id=policy_id,
            clause_id=clause_id,
            attack_scenario=attack.get("attack_scenario", ""),
            matched_rbi_passage_id=str(audit.get("matched_rbi_passage_id", "")),
            violation_detected=as_bool(audit.get("violation_confirmed", False)) and is_supported,
            explanation=f"{audit.get('explanation', '')} [Verification: {verification.get('verification_rationale', '')}]",
            severity=audit.get("severity", "Medium"),
            evidence=evidence,
        )

        # Remediation & Re-Test ASR Loop
        if is_supported:
            remediation = remediate_clause(clause_text, audit)
            patched_text = remediation.get("patched_clause_text", clause_text)
            
            # Re-Test loop using exact same attack set
            retest_report = self.retest_agent.evaluate_patch(
                original_clause=clause_text, 
                patched_clause=patched_text,
                attack_scenario=attack
            )
            
            remediation["asr_before"] = retest_report["asr_before"]
            remediation["asr_after"] = retest_report["asr_after"]
            remediation["retest_metrics"] = retest_report
            
            status = "remediated" if retest_report["retest_passed"] else "remediation_flagged"
        else:
            remediation = {
                "patched_clause_text": clause_text,
                "remediation_rationale": "Remediation skipped due to unverified evidence passage (failed closed).",
                "asr_before": 0.0,
                "asr_after": 0.0,
                "status": "Flagged_Unverified"
            }
            status = "flagged_unverified"

        remediation_id = insert_remediation_result(
            finding_id=finding_id,
            patched_clause_text=remediation.get("patched_clause_text", ""),
            asr_before=float(remediation.get("asr_before", 0.0)),
            asr_after=float(remediation.get("asr_after", 0.0)),
            status=remediation.get("status", "Resolved")
        )

        return {
            "status": status,
            "policy_id": policy_id,
            "clause_id": clause_id,
            "finding_id": finding_id,
            "remediation_id": remediation_id,
            "risk": risk,
            "attack": attack,
            "audit": audit,
            "verification": verification,
            "remediation": remediation
        }