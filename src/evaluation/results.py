import json
import logging
import os

logger = logging.getLogger(__name__)

ML_RESULTS_PATH = "data/benchmarks/ml_results.json"
RETRIEVAL_RESULTS_PATH = "data/benchmarks/retrieval_results.json"
BENCHMARK_PATH = "data/benchmarks/policy_loophole_eval_benchmark.json"


def _load(path):
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
    if not strategy_result:
        return None
    return {
        "clauses_scored": strategy_result.get("clauses_scored"),
        "seconds": strategy_result.get("seconds"),
        "macro": strategy_result.get("macro"),
    }


def benchmark_summary():
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
        "shuffled_label_control": data.get("shuffled_label_control"),
        "gate_behaviour": data.get("gate_behaviour"),
        "explainability": data.get("explainability"),
        "caveats": data.get("caveats", []),
    }


def retrieval_summary():
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
    return {
        "ml": ml_summary(),
        "retrieval": retrieval_summary(),
        "benchmark": benchmark_summary(),
    }

