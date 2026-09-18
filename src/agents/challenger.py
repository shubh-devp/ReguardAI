
import logging
from concurrent.futures import ThreadPoolExecutor

from src.agents.llm import as_bool, ensure_api_key, generate_json

logger = logging.getLogger(__name__)

SEVERITIES = ("Low", "Medium", "High")

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
    if not attacks:
        return None
    return max((attack["severity"] for attack in attacks), key=SEVERITIES.index)


def select_primary(attacks):
    flagged = [attack for attack in attacks if attack["vulnerability_detected"]]
    if not flagged:
        return None

    order = [surface["id"] for surface in SURFACES]
    return max(
        flagged,
        key=lambda attack: (SEVERITIES.index(attack["severity"]), -order.index(attack["surface"])),
    )


def generate_adversarial_attacks(clause_text, max_workers=None):
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


