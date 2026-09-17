"""The measured evaluation results, shaped for the dashboard.

Every number served from here was produced by running ``evaluate_ml.py`` and
``evaluate_retrieval.py``; nothing is written by hand. The dashboard reads the
same artefact the README quotes, so the two cannot drift apart.

The bulky per-clause arrays are dropped: the dashboard shows the macro figures,
and shipping 96 rows of per-clause scores to a browser is noise.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

ML_RESULTS_PATH = "data/benchmarks/ml_results.json"
RETRIEVAL_RESULTS_PATH = "data/benchmarks/retrieval_results.json"
BENCHMARK_PATH = "data/benchmarks/policy_loophole_eval_benchmark.json"


def _load(path):
    """Read one results file, or return None so the caller can say it is missing."""
    if not os.path.exists(path):
        logger.warning("Evaluation results not found at %s", path)
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        logger.exception("Could not read evaluation results from %s", path)
        return None


def _macro(strategy_result):
    """The strategy's headline scores, without the per-clause breakdown."""
    if not strategy_result:
        return None
    return {
        "clauses_scored": strategy_result.get("clauses_scored"),
        "seconds": strategy_result.get("seconds"),
        "macro": strategy_result.get("macro"),
    }


def benchmark_summary():
    """What the labelled benchmark is: size, balance, split sizes, how it is used."""
    data = _load(BENCHMARK_PATH)
    if data is None:
        return None

    return {
        "benchmark_id": data.get("benchmark_id"),
        "domain": data.get("domain"),
        "description": data.get("description"),
        "label_balance": data.get("label_balance"),
        "split_sizes": data.get("split_sizes"),
        "usage_notes": data.get("usage_notes"),
        "total_clauses": len(data.get("clauses") or []),
    }


def ml_summary():
    """Cross-validation scores per candidate model, plus the shipped choice."""
    data = _load(ML_RESULTS_PATH)
    if data is None:
        return None

    candidates = {
        name: {
            "description": entry.get("description"),
            "summary": entry.get("summary"),
            "pooled_confusion_matrix": entry.get("pooled_confusion_matrix"),
        }
        for name, entry in (data.get("cross_validation") or {}).items()
    }

    return {
        "dataset": data.get("dataset"),
        "candidates": candidates,
        "shipped_model": data.get("shipped_model"),
        # The shuffled-label run is the honesty check: if the model scores about
        # the same on random labels, it has learned nothing.
        "shuffled_label_control": data.get("shuffled_label_control"),
        "gate_behaviour": data.get("gate_behaviour"),
        "explainability": data.get("explainability"),
        "caveats": data.get("caveats", []),
    }


def retrieval_summary():
    """Recall@K, MRR and nDCG@K per retrieval strategy, plus which ships."""
    data = _load(RETRIEVAL_RESULTS_PATH)
    if data is None:
        return None

    return {
        "dataset": data.get("dataset"),
        "production_k": data.get("production_k"),
        "candidate_k": data.get("candidate_k"),
        "strategies": {
            name: _macro(result) for name, result in (data.get("strategies") or {}).items()
        },
        "verdict": data.get("verdict"),
        "caveats": data.get("caveats", []),
    }


def headline():
    """Everything the dashboard needs about measured performance, in one payload."""
    return {
        "ml": ml_summary(),
        "retrieval": retrieval_summary(),
        "benchmark": benchmark_summary(),
    }








# """Packages and serves pre-calculated evaluation results for the frontend dashboard."""

# from pathlib import Path
# import json
# import os

# ML_RESULTS_PATH = Path("data/benchmarks/ml_results.json")
# RETRIEVAL_RESULTS_PATH = Path("data/benchmarks/retrieval_results.json")
# BENCHMARK_PATH = Path("data/benchmarks/policy_loophole_eval_benchmark.json")


# def _load(path):
#     """Load and parse an evaluation JSON file safely."""
#     target = Path(path)
#     if not target.exists():
#         print(f"Notice: Evaluation result file not found at {target}.")
#         return None
#     try:
#         with open(target, "r", encoding="utf-8") as f:
#             return json.load(f)
#     except (OSError, ValueError) as error:
#         print(f"Error parsing evaluation file {target}: {error}")
#         return None


# def _macro(strategy_result):
#     """Extract strategy headline metrics while stripping verbose per-clause arrays."""
#     if not strategy_result:
#         return None
#     return {
#         "clauses_scored": strategy_result.get("clauses_scored"),
#         "seconds": strategy_result.get("seconds"),
#         "macro": strategy_result.get("macro"),
#     }


# def benchmark_summary():
#     """Return dataset details including balance, splits, and scope."""
#     data = _load(BENCHMARK_PATH)
#     if data is None:
#         return None

#     return {
#         "benchmark_id": data.get("benchmark_id"),
#         "domain": data.get("domain"),
#         "description": data.get("description"),
#         "label_balance": data.get("label_balance"),
#         "split_sizes": data.get("split_sizes"),
#         "usage_notes": data.get("usage_notes"),
#         "total_clauses": len(data.get("clauses") or []),
#     }


# def ml_summary():
#     """Return cross-validation metrics, model candidate options, and control baselines."""
#     data = _load(ML_RESULTS_PATH)
#     if data is None:
#         return None

#     candidates = {
#         name: {
#             "description": entry.get("description"),
#             "summary": entry.get("summary"),
#             "pooled_confusion_matrix": entry.get("pooled_confusion_matrix"),
#         }
#         for name, entry in (data.get("cross_validation") or {}).items()
#     }

#     return {
#         "dataset": data.get("dataset"),
#         "candidates": candidates,
#         "shipped_model": data.get("shipped_model"),
#         "shuffled_label_control": data.get("shuffled_label_control"),
#         "gate_behaviour": data.get("gate_behaviour"),
#         "explainability": data.get("explainability"),
#         "caveats": data.get("caveats", []),
#     }


# def retrieval_summary():
#     """Return retrieval performance stats and strategy comparisons."""
#     data = _load(RETRIEVAL_RESULTS_PATH)
#     if data is None:
#         return None

#     return {
#         "dataset": data.get("dataset"),
#         "production_k": data.get("production_k"),
#         "candidate_k": data.get("candidate_k"),
#         "strategies": {
#             name: _macro(result) for name, result in (data.get("strategies") or {}).items()
#         },
#         "verdict": data.get("verdict"),
#         "caveats": data.get("caveats", []),
#     }


# def headline():
#     """Aggregate all evaluation metrics into a single cohesive payload for the UI."""
#     return {
#         "ml": ml_summary(),
#         "retrieval": retrieval_summary(),
#         "benchmark": benchmark_summary(),
#     }