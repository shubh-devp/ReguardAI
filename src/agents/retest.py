import logging
from concurrent.futures import ThreadPoolExecutor

from src.agents.auditor import RegulatoryAuditor
from src.agents.llm import as_bool
from src.agents.verifier import verify_evidence_batch

logger = logging.getLogger(__name__)


class ReTestAgent:

    def __init__(self):
        self.auditor = RegulatoryAuditor()

    def judge_clause(self, clause_text, attacks):
        audit = self.auditor.audit_clause_batch(clause_text, attacks)
        if audit["error"]:
            return [None] * len(attacks)

        verification = verify_evidence_batch(
            clause_text,
            audit["findings"],
            [block.get("passage_text") for block in audit["evidence"]],
        )
        if verification["error"]:
            return [None] * len(attacks)

        judged = []
        for finding, check in zip(audit["findings"], verification["verdicts"]):
            if finding is None or check is None:
                # The model did not answer about this attack, so it is unmeasured
                # rather than blocked.
                judged.append(None)
                continue
            judged.append(
                as_bool(finding.get("violation_confirmed"))
                and as_bool(check.get("is_supported"))
            )
        return judged

    def evaluate_patch(self, original_clause, patched_clause, attacks, max_workers=None):
        """Measure ASR before and after, and whether the patch closed the gap."""
        if not attacks:
            return {
                "asr_before": None,
                "asr_after": None,
                "risk_reduction_delta": None,
                "total_attacks": 0,
                "measured_attacks": 0,
                "unmeasured_attacks": 0,
                "measurement_complete": False,
                "original_successes": 0,
                "patched_successes": 0,
                "remediation_success_rate": None,
                "retest_passed": False,
                "verdict": "not_measured",
                "per_attack": [],
            }


        with ThreadPoolExecutor(max_workers=max_workers or 2) as pool:
            before_future = pool.submit(self.judge_clause, original_clause, attacks)
            after_future = pool.submit(self.judge_clause, patched_clause, attacks)
            before = before_future.result()
            after = after_future.result()

        comparisons = [
            {
                "surface": attack.get("surface"),
                "title": attack.get("title"),
                "severity": attack.get("severity"),
                "succeeded_before": before[index],
                "succeeded_after": after[index],
            }
            for index, attack in enumerate(attacks)
        ]

        total = len(comparisons)
        before_measured = [row for row in comparisons if row["succeeded_before"] is not None]
        after_measured = [row for row in comparisons if row["succeeded_after"] is not None]
        unmeasured = sum(
            1
            for row in comparisons
            if row["succeeded_before"] is None or row["succeeded_after"] is None
        )

        original_successes = sum(1 for row in before_measured if row["succeeded_before"])
        patched_successes = sum(1 for row in after_measured if row["succeeded_after"])

        asr_before = round(original_successes / len(before_measured), 4) if before_measured else None
        asr_after = round(patched_successes / len(after_measured), 4) if after_measured else None
        measured = min(len(before_measured), len(after_measured))


        closed = original_successes - patched_successes
        remediation_success_rate = (
            round(closed / original_successes, 4)
            if original_successes and asr_before is not None and asr_after is not None
            else None
        )

        verdict = self._verdict(
            original_successes,
            patched_successes,
            len(before_measured),
            len(after_measured),
        )

        for row in comparisons:
            row["blocked_by_patch"] = row["succeeded_before"] is True and row["succeeded_after"] is False
            row["regression"] = row["succeeded_after"] is True and row["succeeded_before"] is False
            row["measured"] = row["succeeded_before"] is not None and row["succeeded_after"] is not None

        return {
            "asr_before": asr_before,
            "asr_after": asr_after,
            "risk_reduction_delta": (
                round(asr_before - asr_after, 4)
                if asr_before is not None and asr_after is not None
                else None
            ),
            "total_attacks": total,
            "measured_attacks": measured,
            "unmeasured_attacks": unmeasured,
            "measurement_complete": unmeasured == 0,
            "original_successes": original_successes,
            "patched_successes": patched_successes,
            "remediation_success_rate": remediation_success_rate,
            "retest_passed": verdict == "fully_mitigated" and unmeasured == 0,
            "verdict": verdict,
            "per_attack": comparisons,
        }

    @staticmethod
    def _verdict(original_successes, patched_successes, before_measured, after_measured):
        if before_measured == 0 or after_measured == 0:
            return "not_measured"
        if original_successes == 0:
            return "no_vulnerability_detected"
        if patched_successes == 0:
            return "fully_mitigated"
        if patched_successes < original_successes:
            return "partially_mitigated"
        return "not_mitigated"

