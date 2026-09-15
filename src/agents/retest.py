from src.agents.auditor import RegulatoryAuditor
from src.agents.llm import as_bool
from src.agents.verifier import verify_evidence


class ReTestAgent:
    """
    Re-Test Agent: measures whether remediation actually reduced the attack
    success rate.

    The same probe set is run against the original clause and the patched clause,
    and a probe counts as a successful attack only when the Auditor confirms a
    violation *and* the Evidence Verifier accepts the passage behind it.

    Note: the verdicts come from live model calls, so ASR here is an estimate on
    a three-probe set rather than a reproducible measurement. Widening the probe
    set is tracked as outstanding work.
    """
    def __init__(self):
        self.auditor = RegulatoryAuditor()

    def _attacks_succeed(self, clause_text: str, probes) -> int:
        """Run every probe against one clause and count the successful attacks."""
        successes = 0
        for probe in probes:
            audit = self.auditor.audit_clause(clause_text, {"attack_scenario": probe})
            passage = audit.get("retrieved_passage", "Statutory RBI regulatory guideline.")
            verification = verify_evidence(clause_text, audit, passage)

            # A probe only counts when the violation is confirmed and the evidence
            # behind it is verified, so an unsupported claim cannot raise ASR.
            if as_bool(audit.get("violation_confirmed", False)) and as_bool(verification.get("is_supported", False)):
                successes += 1
        return successes

    def evaluate_patch(self, original_clause: str, patched_clause: str, attack_scenario: dict) -> dict:
        attack_text = attack_scenario.get("attack_scenario", "Exploit regulatory loophole.")

        # The same probe strings are replayed against both clauses.
        attack_probes = [
            attack_text,
            f"Assuming clause states: {original_clause}, apply exploit: {attack_text}",
            f"Bypass condition under: {attack_text}"
        ]

        total_attacks = len(attack_probes)
        orig_successes = self._attacks_succeed(original_clause, attack_probes)
        patch_successes = self._attacks_succeed(patched_clause, attack_probes)

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