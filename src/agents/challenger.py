"""Adversarial red-team agents, one per compliance surface.

The pipeline used to run a single attacker, which produced a single attack
scenario; the Re-Test stage then rephrased that one scenario three times and
called it an attack set. That overstates coverage, because all three probes come
from the same idea.

This module runs one attacker per surface. Each has its own prompt and its own
lens, the calls are independent so they run in parallel, and their verdicts are
then aggregated into an agreement summary. Where the attackers disagree, that is
recorded rather than hidden: a surface that finds a loophole while the others do
not is a signal worth surfacing to a reviewer.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from src.agents.llm import as_bool, ensure_api_key, generate_json

logger = logging.getLogger(__name__)

SEVERITIES = ("Low", "Medium", "High")

# The distinct compliance surfaces the auditors reason over. Each is a separate
# agent with a separate lens, not a rephrasing of one query.
SURFACES = (
    {
        "id": "disclosure",
        "title": "APR and Key Fact Statement disclosure",
        "lens": (
            "Transparency of the all-inclusive cost of credit: whether the APR and the Key Fact "
            "Statement disclose interest, processing fees, documentation charges and any bundled "
            "insurance together, and whether mandatory fees are left out of the headline figure."
        ),
    },
    {
        "id": "charges",
        "title": "Penal charges and fees",
        "lens": (
            "Penal charges and compounding: whether penal charges are levied as a penal interest "
            "added to the rate, whether they are capitalised or compounded, whether they are "
            "excessive, and whether any fee duplicates a permitted one-time charge."
        ),
    },
    {
        "id": "cooling_off",
        "title": "Cooling-off and exit rights",
        "lens": (
            "The borrower's right to exit: whether the cooling-off period exists and is at least "
            "one day, whether exit is penalty-free beyond a reasonable disclosed one-time "
            "processing fee, and whether any exit charge or condition obstructs it."
        ),
    },
    {
        "id": "data_consent",
        "title": "Data sharing, consent and third parties",
        "lens": (
            "Data handling and third parties: whether consent for data sharing is explicit and "
            "purpose-limited, whether third-party or LSP arrangements are disclosed, and whether "
            "the borrower can withdraw consent."
        ),
    },
)

PROMPT = """\
You are the {title} red-team agent for Reguard AI, an RBI digital-lending compliance engine.

Your lens is narrow on purpose. Judge the clause only through it:
{lens}

Policy clause under test:
"{clause_text}"

Look for a concrete way this clause could be exploited or could breach the
Reserve Bank of India's digital lending directions through your lens. A clause is
only an exploit if a borrower could actually be harmed by it, not merely because
it is worded loosely. If your lens does not apply to this clause, say so by
setting vulnerability_detected to false.

Return raw JSON only, with exactly these keys:
- "vulnerability_detected": boolean
- "severity": string, one of "Low", "Medium", "High"
- "attack_scenario": string, one concrete scenario in which a borrower is harmed
- "explanation": string, the regulatory reasoning for your verdict
"""


def _normalise(raw, surface):
    """Coerce one agent's reply into a fixed shape.

    Agent replies are parsed JSON rather than a validated schema, so a field can
    be missing, the wrong type, or an unexpected severity. Everything is coerced
    here so the rest of the pipeline never has to guess.
    """
    severity = str(raw.get("severity") or "").strip().title()
    if severity not in SEVERITIES:
        severity = "Medium"

    return {
        "surface": surface["id"],
        "title": surface["title"],
        "vulnerability_detected": as_bool(raw.get("vulnerability_detected", False)),
        "severity": severity,
        "attack_scenario": str(raw.get("attack_scenario") or "").strip(),
        "explanation": str(raw.get("explanation") or "").strip(),
        "failed": False,
    }


def _failed_attack(surface, reason):
    """A surface that could not be assessed is recorded as failed, not as clear."""
    return {
        "surface": surface["id"],
        "title": surface["title"],
        "vulnerability_detected": False,
        "severity": "Low",
        "attack_scenario": "",
        "explanation": f"Agent failed: {reason}",
        "failed": True,
    }


def run_surface(surface, clause_text):
    """Ask one surface agent to attack the clause."""
    prompt = PROMPT.format(
        title=surface["title"], lens=surface["lens"], clause_text=clause_text
    )
    try:
        # Higher temperature than the auditor: this stage is meant to explore.
        return _normalise(generate_json(prompt, temperature=0.6), surface)
    except Exception as error:
        logger.warning("Adversarial agent %s failed: %s", surface["id"], error)
        return _failed_attack(surface, error)


def summarise(attacks):
    """Aggregate the agents' verdicts into an agreement summary.

    Disagreement is reported rather than smoothed over: a single surface finding a
    loophole that the others miss is exactly the case a reviewer should look at.
    """
    if not attacks:
        return {
            "attacks_generated": 0,
            "surfaces_flagged": 0,
            "agreement": 0.0,
            "highest_severity": None,
            "consensus": "no_attacks",
            "flagged_surfaces": [],
            "failed_surfaces": [],
        }

    flagged = [attack for attack in attacks if attack["vulnerability_detected"]]
    failed = [attack for attack in attacks if attack["failed"]]

    if not flagged:
        consensus = "unanimous_clear"
    elif len(flagged) == len(attacks):
        consensus = "unanimous_vulnerable"
    else:
        consensus = "split"

    return {
        "attacks_generated": len(attacks),
        "surfaces_flagged": len(flagged),
        "agreement": round(len(flagged) / len(attacks), 4),
        "highest_severity": highest_severity(flagged),
        "consensus": consensus,
        "flagged_surfaces": [attack["surface"] for attack in flagged],
        "failed_surfaces": [attack["surface"] for attack in failed],
    }


def highest_severity(attacks):
    """The most severe rating among a set of attacks."""
    if not attacks:
        return None
    return max((attack["severity"] for attack in attacks), key=SEVERITIES.index)


def select_primary(attacks):
    """The attack the audit proceeds with.

    The most severe flagged attack wins. Ties break on the surface order in
    ``SURFACES``, so the same clause always yields the same primary attack.
    """
    flagged = [attack for attack in attacks if attack["vulnerability_detected"]]
    if not flagged:
        return None

    order = [surface["id"] for surface in SURFACES]
    return max(
        flagged,
        key=lambda attack: (SEVERITIES.index(attack["severity"]), -order.index(attack["surface"])),
    )


def generate_adversarial_attacks(clause_text, max_workers=None):
    """Run every surface agent in parallel and return their attacks.

    The calls are independent HTTP requests, so threads are safe and the wall
    clock is the slowest single agent rather than the sum of all of them.
    """
    ensure_api_key()

    workers = max_workers or len(SURFACES)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        attacks = list(pool.map(lambda surface: run_surface(surface, clause_text), SURFACES))

    order = [surface["id"] for surface in SURFACES]
    attacks.sort(key=lambda attack: order.index(attack["surface"]))

    summary = summarise(attacks)
    logger.info(
        "Red team: %d/%d surfaces flagged a vulnerability (%s)",
        summary["surfaces_flagged"], summary["attacks_generated"], summary["consensus"],
    )
    return attacks, summary








# """Adversarial red-team agents, running in parallel across multiple compliance surfaces."""

# from concurrent.futures import ThreadPoolExecutor

# from src.agents.llm import as_bool, ensure_api_key, generate_json

# SEVERITIES = ("Low", "Medium", "High")

# # Distinct compliance surfaces evaluated independently in parallel
# SURFACES = [
#     {
#         "id": "disclosure",
#         "title": "APR and Key Fact Statement disclosure",
#         "lens": (
#             "Transparency of the all-inclusive cost of credit: whether the APR and the Key Fact "
#             "Statement disclose interest, processing fees, documentation charges and any bundled "
#             "insurance together, and whether mandatory fees are left out of the headline figure."
#         ),
#     },
#     {
#         "id": "charges",
#         "title": "Penal charges and fees",
#         "lens": (
#             "Penal charges and compounding: whether penal charges are levied as a penal interest "
#             "added to the rate, whether they are capitalised or compounded, whether they are "
#             "excessive, and whether any fee duplicates a permitted one-time charge."
#         ),
#     },
#     {
#         "id": "cooling_off",
#         "title": "Cooling-off and exit rights",
#         "lens": (
#             "The borrower's right to exit: whether the cooling-off period exists and is at least "
#             "one day, whether exit is penalty-free beyond a reasonable disclosed one-time "
#             "processing fee, and whether any exit charge or condition obstructs it."
#         ),
#     },
#     {
#         "id": "data_consent",
#         "title": "Data sharing, consent and third parties",
#         "lens": (
#             "Data handling and third parties: whether consent for data sharing is explicit and "
#             "purpose-limited, whether third-party or LSP arrangements are disclosed, and whether "
#             "the borrower can withdraw consent."
#         ),
#     },
# ]

# PROMPT = """\
# You are the {title} red-team agent for Reguard AI, an RBI digital-lending compliance engine.

# Your lens is narrow on purpose. Judge the clause only through it:
# {lens}

# Policy clause under test:
# "{clause_text}"

# Look for a concrete way this clause could be exploited or could breach the
# Reserve Bank of India's digital lending directions through your lens. A clause is
# only an exploit if a borrower could actually be harmed by it, not merely because
# it is worded loosely. If your lens does not apply to this clause, say so by
# setting vulnerability_detected to false.

# Return raw JSON only, with exactly these keys:
# - "vulnerability_detected": boolean
# - "severity": string, one of "Low", "Medium", "High"
# - "attack_scenario": string, one concrete scenario in which a borrower is harmed
# - "explanation": string, the regulatory reasoning for your verdict
# """


# def _normalize(raw, surface):
#     """Coerce surface agent reply into a stable, consistent schema."""
#     severity = str(raw.get("severity") or "").strip().title()
#     if severity not in SEVERITIES:
#         severity = "Medium"

#     return {
#         "surface": surface["id"],
#         "title": surface["title"],
#         "vulnerability_detected": as_bool(raw.get("vulnerability_detected", False)),
#         "severity": severity,
#         "attack_scenario": str(raw.get("attack_scenario") or "").strip(),
#         "explanation": str(raw.get("explanation") or "").strip(),
#         "failed": False,
#     }


# def _failed_attack(surface, reason):
#     """Record an agent failure safely without assuming compliance."""
#     return {
#         "surface": surface["id"],
#         "title": surface["title"],
#         "vulnerability_detected": False,
#         "severity": "Low",
#         "attack_scenario": "",
#         "explanation": f"Agent failed: {reason}",
#         "failed": True,
#     }


# def run_surface(surface, clause_text):
#     """Execute a single red-team agent query over a specific compliance lens."""
#     prompt = PROMPT.format(
#         title=surface["title"], lens=surface["lens"], clause_text=clause_text
#     )
#     try:
#         # Higher temperature to encourage creative exploratory attack angles
#         return _normalize(generate_json(prompt, temperature=0.6), surface)
#     except Exception as error:
#         print(f"Warning: Adversarial agent {surface['id']} failed: {error}")
#         return _failed_attack(surface, error)


# def summarize(attacks):
#     """Aggregate individual surface verdicts into consensus stats."""
#     if not attacks:
#         return {
#             "attacks_generated": 0,
#             "surfaces_flagged": 0,
#             "agreement": 0.0,
#             "highest_severity": None,
#             "consensus": "no_attacks",
#             "flagged_surfaces": [],
#             "failed_surfaces": [],
#         }

#     flagged = [a for a in attacks if a["vulnerability_detected"]]
#     failed = [a for a in attacks if a["failed"]]

#     if not flagged:
#         consensus = "unanimous_clear"
#     elif len(flagged) == len(attacks):
#         consensus = "unanimous_vulnerable"
#     else:
#         consensus = "split"

#     return {
#         "attacks_generated": len(attacks),
#         "surfaces_flagged": len(flagged),
#         "agreement": round(len(flagged) / len(attacks), 4),
#         "highest_severity": highest_severity(flagged),
#         "consensus": consensus,
#         "flagged_surfaces": [a["surface"] for a in flagged],
#         "failed_surfaces": [a["surface"] for a in failed],
#     }


# def highest_severity(attacks):
#     """Identify the maximum severity rating across a set of active attacks."""
#     if not attacks:
#         return None
#     return max((a["severity"] for a in attacks), key=SEVERITIES.index)


# def select_primary(attacks):
#     """Select the primary attack scenario for audit flow based on severity and order."""
#     flagged = [a for a in attacks if a["vulnerability_detected"]]
#     if not flagged:
#         return None

#     order = [s["id"] for s in SURFACES]
#     return max(
#         flagged,
#         key=lambda a: (SEVERITIES.index(a["severity"]), -order.index(a["surface"])),
#     )


# def generate_adversarial_attacks(clause_text, max_workers=None):
#     """Run all surface agents concurrently in separate threads."""
#     ensure_api_key()

#     workers = max_workers or len(SURFACES)
#     with ThreadPoolExecutor(max_workers=workers) as pool:
#         attacks = list(pool.map(lambda surf: run_surface(surf, clause_text), SURFACES))

#     order = [s["id"] for s in SURFACES]
#     attacks.sort(key=lambda a: order.index(a["surface"]))

#     summary = summarize(attacks)
#     print(f"Red team complete: {summary['surfaces_flagged']}/{summary['attacks_generated']} surfaces flagged ({summary['consensus']})")
#     return attacks, summary