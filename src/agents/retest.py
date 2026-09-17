"""Re-Test agent: did the remediation actually reduce the attack success rate?

Attack Success Rate is measured over the same attack set before and after the
patch, so the comparison is like for like. Each attack is judged by the Auditor
and the Evidence Verifier together, so a finding with no verified evidence behind
it cannot inflate the number.

The earlier version rephrased one attacker's single scenario into three probes and
called that an attack set, and it reported a pass whenever ``asr_after`` was
merely lower than ``asr_before`` - including when nothing had ever been
vulnerable. Both are fixed here: the set comes from the specialised attackers, and
the verdict distinguishes "nothing to fix" from "fixed" from "partly fixed".

Judging is batched. One clause is judged against its whole attack set in a single
Auditor call and a single Verifier call, so a re-test costs four model calls
instead of sixteen. That matters on a rate-limited key: at sixteen calls a single
audit exceeded the free tier's per-minute limit and most of the re-test came back
unmeasured. The attacks are still judged independently inside each reply.

An attack whose judging call fails is recorded as unmeasured rather than as
blocked, and is left out of both rates. A rate-limited model is not evidence that
the patch worked.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from src.agents.auditor import RegulatoryAuditor
from src.agents.llm import as_bool
from src.agents.verifier import verify_evidence_batch

logger = logging.getLogger(__name__)


class ReTestAgent:
    """Measures ASR before and after remediation over the red team's attack set."""

    def __init__(self):
        self.auditor = RegulatoryAuditor()

    def judge_clause(self, clause_text, attacks):
        """Which of these attacks defeat this clause?

        Returns a list aligned with ``attacks`` where each entry is True (the attack
        defeats the clause), False (it is blocked), or None (it could not be
        measured). Two model calls cover the whole set: one to judge the attacks
        and one to verify the citations behind those judgements.

        An attack only counts when the Auditor confirms a violation *and* the
        Verifier accepts the passage behind it.
        """
        audit = self.auditor.audit_clause_batch(clause_text, attacks)
        if audit["error"]:
            return [None] * len(attacks)

        # Each claim is verified against the passage it was judged on, so the
        # evidence check cannot pass on a passage about a different surface.
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

        # The two clauses are judged independently, so they run side by side. Each
        # side is itself a batch, so this is two calls deep rather than two dozen.
        with ThreadPoolExecutor(max_workers=max_workers or 2) as pool:
            before_future = pool.submit(self.judge_clause, original_clause, attacks)
            after_future = pool.submit(self.judge_clause, patched_clause, attacks)
            before = before_future.result()
            after = after_future.result()

        comparisons = [
            {
                "surface": attack.get("surface"),
                # The readable name travels with the row, so the report does not
                # have to show the raw internal key ("cooling_off").
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

        # Each rate is taken over the attacks that were actually measured on that
        # side, so a failed call cannot move the number in either direction.
        asr_before = round(original_successes / len(before_measured), 4) if before_measured else None
        asr_after = round(patched_successes / len(after_measured), 4) if after_measured else None
        measured = min(len(before_measured), len(after_measured))

        # Of the attacks that worked against the original clause, what share did
        # the patch actually stop? This is undefined when nothing worked before.
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
            # Only a clean sweep counts as passed, and only when every attack was
            # actually measured. Reporting a pass for a partial reduction, for a
            # clause that was never vulnerable, or for a half-finished
            # measurement would all overstate what the remediation achieved.
            "retest_passed": verdict == "fully_mitigated" and unmeasured == 0,
            "verdict": verdict,
            "per_attack": comparisons,
        }

    @staticmethod
    def _verdict(original_successes, patched_successes, before_measured, after_measured):
        if before_measured == 0 or after_measured == 0:
            return "not_measured"
        if original_successes == 0:
            # Nothing defeated the original clause, so the patch has not been
            # demonstrated to have fixed anything.
            return "no_vulnerability_detected"
        if patched_successes == 0:
            return "fully_mitigated"
        if patched_successes < original_successes:
            return "partially_mitigated"
        return "not_mitigated"






# """Re-Test agent: evaluates whether remediation effectively reduces the attack success rate."""

# from concurrent.futures import ThreadPoolExecutor

# from src.agents.auditor import RegulatoryAuditor
# from src.agents.llm import as_bool
# from src.agents.verifier import verify_evidence_batch


# class ReTestAgent:
#     """Measures ASR before and after patch application against red-team attacks."""

#     def __init__(self):
#         self.auditor = RegulatoryAuditor()

#     def judge_clause(self, clause_text, attacks):
#         """Evaluate which adversarial attacks successfully defeat a clause."""
#         audit = self.auditor.audit_clause_batch(clause_text, attacks)
#         if audit["error"]:
#             return [None] * len(attacks)

#         verification = verify_evidence_batch(
#             clause_text,
#             audit["findings"],
#             [block.get("passage_text") for block in audit["evidence"]],
#         )
#         if verification["error"]:
#             return [None] * len(attacks)

#         judged = []
#         for finding, check in zip(audit["findings"], verification["verdicts"]):
#             if finding is None or check is None:
#                 judged.append(None)
#                 continue
#             judged.append(
#                 as_bool(finding.get("violation_confirmed"))
#                 and as_bool(check.get("is_supported"))
#             )
#         return judged

#     def evaluate_patch(self, original_clause, patched_clause, attacks, max_workers=None):
#         """Compare ASR before and after patching to measure vulnerability mitigation."""
#         if not attacks:
#             return {
#                 "asr_before": None,
#                 "asr_after": None,
#                 "risk_reduction_delta": None,
#                 "total_attacks": 0,
#                 "measured_attacks": 0,
#                 "unmeasured_attacks": 0,
#                 "measurement_complete": False,
#                 "original_successes": 0,
#                 "patched_successes": 0,
#                 "remediation_success_rate": None,
#                 "retest_passed": False,
#                 "verdict": "not_measured",
#                 "per_attack": [],
#             }

#         # Evaluate original and patched clauses concurrently in threads
#         with ThreadPoolExecutor(max_workers=max_workers or 2) as pool:
#             before_future = pool.submit(self.judge_clause, original_clause, attacks)
#             after_future = pool.submit(self.judge_clause, patched_clause, attacks)
#             before = before_future.result()
#             after = after_future.result()

#         comparisons = [
#             {
#                 "surface": attack.get("surface"),
#                 "title": attack.get("title"),
#                 "severity": attack.get("severity"),
#                 "succeeded_before": before[idx],
#                 "succeeded_after": after[idx],
#             }
#             for idx, attack in enumerate(attacks)
#         ]

#         total = len(comparisons)
#         before_measured = [r for r in comparisons if r["succeeded_before"] is not None]
#         after_measured = [r for r in comparisons if r["succeeded_after"] is not None]
#         unmeasured = sum(
#             1 for r in comparisons if r["succeeded_before"] is None or r["succeeded_after"] is None
#         )

#         original_successes = sum(1 for r in before_measured if r["succeeded_before"])
#         patched_successes = sum(1 for r in after_measured if r["succeeded_after"])

#         asr_before = round(original_successes / len(before_measured), 4) if before_measured else None
#         asr_after = round(patched_successes / len(after_measured), 4) if after_measured else None
#         measured = min(len(before_measured), len(after_measured))

#         closed = original_successes - patched_successes
#         remediation_success_rate = (
#             round(closed / original_successes, 4)
#             if original_successes and asr_before is not None and asr_after is not None
#             else None
#         )

#         verdict = self._verdict(
#             original_successes,
#             patched_successes,
#             len(before_measured),
#             len(after_measured),
#         )

#         for r in comparisons:
#             r["blocked_by_patch"] = r["succeeded_before"] is True and r["succeeded_after"] is False
#             r["regression"] = r["succeeded_after"] is True and r["succeeded_before"] is False
#             r["measured"] = r["succeeded_before"] is not None and r["succeeded_after"] is not None

#         return {
#             "asr_before": asr_before,
#             "asr_after": asr_after,
#             "risk_reduction_delta": (
#                 round(asr_before - asr_after, 4)
#                 if asr_before is not None and asr_after is not None
#                 else None
#             ),
#             "total_attacks": total,
#             "measured_attacks": measured,
#             "unmeasured_attacks": unmeasured,
#             "measurement_complete": unmeasured == 0,
#             "original_successes": original_successes,
#             "patched_successes": patched_successes,
#             "remediation_success_rate": remediation_success_rate,
#             "retest_passed": verdict == "fully_mitigated" and unmeasured == 0,
#             "verdict": verdict,
#             "per_attack": comparisons,
#         }

#     @staticmethod
#     def _verdict(original_successes, patched_successes, before_measured, after_measured):
#         if before_measured == 0 or after_measured == 0:
#             return "not_measured"
#         if original_successes == 0:
#             return "no_vulnerability_detected"
#         if patched_successes == 0:
#             return "fully_mitigated"
#         if patched_successes < original_successes:
#             return "partially_mitigated"
#         return "not_mitigated"