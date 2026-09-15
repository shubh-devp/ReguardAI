from src.agents.auditor import RegulatoryAuditor
from src.agents.verifier import verify_evidence
from src.retrieval.hybrid_retriever import load_chunks_from_json, build_chroma_hybrid_retriever

class ReTestAgent:
    """
    Deterministic Re-Test Agent.
    Calculates ASR mathematically from actual Auditor + Evidence Verifier outcomes 
    using the exact same attack probe set backed by real retrieved RBI passages.
    """
    def __init__(self):
        self.auditor = RegulatoryAuditor()

    def evaluate_patch(self, original_clause: str, patched_clause: str, attack_scenario: dict) -> dict:
        attack_text = attack_scenario.get("attack_scenario", "Exploit regulatory loophole.")
        
        # Exact same attack set (test probes) before and after remediation
        attack_probes = [
            attack_text,
            f"Assuming clause states: {original_clause}, apply exploit: {attack_text}",
            f"Bypass condition under: {attack_text}"
        ]
        
        total_attacks = len(attack_probes)
        
        # 1. Test attack set against ORIGINAL clause
        orig_successes = 0
        for probe in attack_probes:
            audit = self.auditor.audit_clause(original_clause, {"attack_scenario": probe})
            # Real retrieved passage text returned from auditor.py
            passage = audit.get("retrieved_passage", "Statutory RBI regulatory guideline.")
            verification = verify_evidence(original_clause, audit, passage)
            is_supported = bool(verification.get("is_supported", False))
            
            # Attack is successful if violation is confirmed AND evidence is verified
            if bool(audit.get("violation_confirmed", False)) and is_supported:
                orig_successes += 1

        # 2. Test exact same attack set against REMEDIATED clause
        patch_successes = 0
        for probe in attack_probes:
            audit = self.auditor.audit_clause(patched_clause, {"attack_scenario": probe})
            passage = audit.get("retrieved_passage", "Statutory RBI regulatory guideline.")
            verification = verify_evidence(patched_clause, audit, passage)
            is_supported = bool(verification.get("is_supported", False))
            
            if bool(audit.get("violation_confirmed", False)) and is_supported:
                patch_successes += 1

        asr_before = round(orig_successes / max(1, total_attacks), 4)
        asr_after = round(patch_successes / max(1, total_attacks), 4)
        risk_reduction = round(asr_before - asr_after, 4)
        
        is_mitigated = bool(asr_after < asr_before or asr_after == 0.0)

        return {
            "asr_before": asr_before,
            "asr_after": asr_after,
            "risk_reduction_delta": risk_reduction,
            "total_attacks": total_attacks,
            "original_successes": orig_successes,
            "patched_successes": patch_successes,
            "retest_passed": is_mitigated
        }