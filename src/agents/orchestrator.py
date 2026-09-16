# import json
# import logging

# from src.models.risk_classifier import PolicyRiskClassifier
# from src.agents.challenger import generate_adversarial_attacks, select_primary
# from src.agents.auditor import RegulatoryAuditor
# from src.agents.verifier import verify_evidence
# from src.agents.remediator import remediate_clause
# from src.agents.retest import ReTestAgent
# from src.agents.llm import as_bool
# from src.retrieval import temporal
# from src.database.sql_manager import (
#     init_db,
#     insert_policy,
#     insert_clause,
#     insert_audit_finding,
#     insert_remediation_result
# )

# logger = logging.getLogger(__name__)


# def _asr_value(value):
#     """ASR is stored as a number, or NULL when it was never measured."""
#     return None if value is None else float(value)


# class ReguardOrchestrator:
#     def __init__(self):
#         init_db()
#         self.classifier = PolicyRiskClassifier()
#         self.auditor = RegulatoryAuditor()
#         self.retest_agent = ReTestAgent()

#     def run(self, policy_name: str, full_text: str, clause_text: str) -> dict:
#         policy_id = insert_policy(policy_name, full_text)
        
#         # ML / NLP Risk Triage
#         risk = self.classifier.predict_risk(clause_text)
#         clause_id = insert_clause(
#             policy_id=policy_id,
#             clause_text=clause_text,
#             actor="Lender",
#             action="Clause Execution",
#             limit_val="N/A",
#             condition="Default",
#             risk_score=risk["risk_score"]
#         )

#         if not risk["requires_red_teaming"]:
#             return {
#                 "status": "compliant",
#                 "policy_id": policy_id,
#                 "clause_id": clause_id,
#                 "risk": risk,
#                 "evidence": {},
#                 "red_team": None,
#             }

#         # Red team: one adversarial agent per compliance surface, run in parallel.
#         attacks, red_team = generate_adversarial_attacks(clause_text)
#         attack = select_primary(attacks)

#         if attack is None:
#             # No surface found a way to exploit the clause, so there is nothing to
#             # audit. Spending further calls on it would only invent a finding.
#             logger.info("No surface flagged a vulnerability for clause %r", clause_text[:60])
#             return {
#                 "status": "no_vulnerability_detected",
#                 "policy_id": policy_id,
#                 "clause_id": clause_id,
#                 "risk": risk,
#                 "evidence": {},
#                 "attack": None,
#                 "attacks": attacks,
#                 "red_team": red_team,
#             }

#         # Hybrid RAG & Auditor Agent
#         audit = self.auditor.audit_clause(clause_text, attack)
#         retrieved_passage = audit.get("retrieved_passage") or audit.get("explanation", "RBI regulatory context.")

#         # Evidence Verifier Agent (Fail-Closed: default to False)
#         verification = verify_evidence(clause_text, audit, retrieved_passage)
#         is_supported = as_bool(verification.get("is_supported", False))
#         confidence = verification.get("confidence_score")
#         evidence = audit.get("evidence") or {}
#         currency = evidence.get("currency") or {}

#         if not temporal.reliance_safe(currency):
#             # The cited rule has been replaced or withdrawn. Verifying against it
#             # would produce a confident finding grounded in a rule that no longer
#             # applies, so the finding is recorded but remediation is blocked.
#             logger.warning(
#                 "Retrieved evidence is not safe to rely on (%s); failing closed",
#                 "; ".join(currency.get("warnings") or ["superseded"]),
#             )
#             is_supported = False

#         if isinstance(confidence, (int, float)) and confidence < 0.5:
#             # A low-confidence verification is not strong enough to justify an
#             # automatic rewrite, so it is reported rather than acted on.
#             logger.warning(
#                 "Verifier confidence %.2f is below the 0.5 threshold for clause %r",
#                 confidence, clause_text[:60],
#             )

#         finding_id = insert_audit_finding(
#             policy_id=policy_id,
#             clause_id=clause_id,
#             attack_scenario=attack.get("attack_scenario", ""),
#             matched_rbi_passage_id=str(audit.get("matched_rbi_passage_id", "")),
#             violation_detected=as_bool(audit.get("violation_confirmed", False)) and is_supported,
#             explanation=f"{audit.get('explanation', '')} [Verification: {verification.get('verification_rationale', '')}]",
#             severity=audit.get("severity", "Medium"),
#             evidence=evidence,
#         )

#         # Remediation & Re-Test ASR Loop
#         if is_supported:
#             remediation = remediate_clause(clause_text, audit)
#             patched_text = remediation.get("patched_clause_text", clause_text)

#             # The whole attack set is replayed against the patched clause, so ASR
#             # before and ASR after are measured over the same attacks.
#             retest_report = self.retest_agent.evaluate_patch(
#                 original_clause=clause_text,
#                 patched_clause=patched_text,
#                 attacks=attacks,
#             )

#             remediation["asr_before"] = retest_report["asr_before"]
#             remediation["asr_after"] = retest_report["asr_after"]
#             remediation["retest_metrics"] = retest_report

#             # The remediator describes its own output ("Resolved"), but only the
#             # re-test knows whether the patch actually worked. Storing the agent's
#             # own label would let a patch that still fails two of three attacks be
#             # filed as resolved.
#             remediation["agent_status"] = remediation.get("status")
#             remediation["status"] = retest_report["verdict"]

#             status = "remediated" if retest_report["retest_passed"] else "remediation_flagged"
#         else:
#             remediation = {
#                 "patched_clause_text": clause_text,
#                 "remediation_rationale": "Remediation skipped due to unverified evidence passage (failed closed).",
#                 "asr_before": None,
#                 "asr_after": None,
#                 "agent_status": None,
#                 "status": "flagged_unverified",
#             }
#             status = "flagged_unverified"

#         remediation_id = insert_remediation_result(
#             finding_id=finding_id,
#             patched_clause_text=remediation.get("patched_clause_text", ""),
#             asr_before=_asr_value(remediation.get("asr_before")),
#             asr_after=_asr_value(remediation.get("asr_after")),
#             status=remediation.get("status", "not_measured")
#         )

#         return {
#             "status": status,
#             "policy_id": policy_id,
#             "clause_id": clause_id,
#             "finding_id": finding_id,
#             "remediation_id": remediation_id,
#             "risk": risk,
#             "attack": attack,
#             "attacks": attacks,
#             "red_team": red_team,
#             "audit": audit,
#             "verification": verification,
#             "remediation": remediation
#         }



"""Central execution pipeline for the Reguard multi-agent compliance auditor."""

from src.models.risk_classifier import PolicyRiskClassifier
from src.agents.challenger import generate_adversarial_attacks, select_primary
from src.agents.auditor import RegulatoryAuditor
from src.agents.verifier import verify_evidence
from src.agents.remediator import remediate_clause
from src.agents.retest import ReTestAgent
from src.agents.llm import as_bool
from src.retrieval import temporal
from src.database.sql_manager import (
    init_db,
    insert_policy,
    insert_clause,
    insert_audit_finding,
    insert_remediation_result
)


def _format_asr_value(val):
    """Return float representation of ASR score or None if unmeasured."""
    return None if val is None else float(val)


class ReguardOrchestrator:
    """Coordinates risk triage, adversarial red-teaming, auditing, and remediation."""

    def __init__(self):
        init_db()
        self.classifier = PolicyRiskClassifier()
        self.auditor = RegulatoryAuditor()
        self.retest_agent = ReTestAgent()

    def run(self, policy_name: str, full_text: str, clause_text: str) -> dict:
        policy_id = insert_policy(policy_name, full_text)
        
        # Step 1: Initial ML risk screening
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
            return {
                "status": "compliant",
                "policy_id": policy_id,
                "clause_id": clause_id,
                "risk": risk,
                "evidence": {},
                "red_team": None,
            }

        # Step 2: Generate adversarial attack angles
        attacks, red_team = generate_adversarial_attacks(clause_text)
        attack = select_primary(attacks)

        if attack is None:
            print(f"Notice: No exploitation vectors discovered for clause snippet: {clause_text[:60]!r}")
            return {
                "status": "no_vulnerability_detected",
                "policy_id": policy_id,
                "clause_id": clause_id,
                "risk": risk,
                "evidence": {},
                "attack": None,
                "attacks": attacks,
                "red_team": red_team,
            }

        # Step 3: Run RAG audit agent
        audit = self.auditor.audit_clause(clause_text, attack)
        retrieved_passage = audit.get("retrieved_passage") or audit.get("explanation", "RBI regulatory context.")

        # Step 4: Verify evidence validity (Fail-Closed default)
        verification = verify_evidence(clause_text, audit, retrieved_passage)
        is_supported = as_bool(verification.get("is_supported", False))
        confidence = verification.get("confidence_score")
        evidence = audit.get("evidence") or {}
        currency = evidence.get("currency") or {}

        if not temporal.reliance_safe(currency):
            print("Warning: Retrieved regulatory evidence is outdated or superseded; failing closed.")
            is_supported = False

        if isinstance(confidence, (int, float)) and confidence < 0.5:
            print(f"Warning: Verifier confidence {confidence:.2f} is below safety threshold.")

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

        # Step 5: Remediation and Re-Test Loop
        if is_supported:
            remediation = remediate_clause(clause_text, audit)
            patched_text = remediation.get("patched_clause_text", clause_text)

            retest_report = self.retest_agent.evaluate_patch(
                original_clause=clause_text,
                patched_clause=patched_text,
                attacks=attacks,
            )

            remediation["asr_before"] = retest_report["asr_before"]
            remediation["asr_after"] = retest_report["asr_after"]
            remediation["retest_metrics"] = retest_report

            remediation["agent_status"] = remediation.get("status")
            remediation["status"] = retest_report["verdict"]

            status = "remediated" if retest_report["retest_passed"] else "remediation_flagged"
        else:
            remediation = {
                "patched_clause_text": clause_text,
                "remediation_rationale": "Remediation skipped due to unverified evidence passage (failed closed).",
                "asr_before": None,
                "asr_after": None,
                "agent_status": None,
                "status": "flagged_unverified",
            }
            status = "flagged_unverified"

        remediation_id = insert_remediation_result(
            finding_id=finding_id,
            patched_clause_text=remediation.get("patched_clause_text", ""),
            asr_before=_format_asr_value(remediation.get("asr_before")),
            asr_after=_format_asr_value(remediation.get("asr_after")),
            status=remediation.get("status", "not_measured")
        )

        return {
            "status": status,
            "policy_id": policy_id,
            "clause_id": clause_id,
            "finding_id": finding_id,
            "remediation_id": remediation_id,
            "risk": risk,
            "attack": attack,
            "attacks": attacks,
            "red_team": red_team,
            "audit": audit,
            "verification": verification,
            "remediation": remediation
        }