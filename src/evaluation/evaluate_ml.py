"""Honest scoring for the clause risk classifier.

Every number here is measured on the labelled benchmark in ``data/benchmarks``,
which links each clause to the RBI passage that justifies its label. The previous
evaluation trained on eight hand-written sentences repeated five times, so
identical sentences appeared in both the train and test halves and the reported
score measured memorisation rather than generalisation.

Two things make the numbers here interpretable rather than decorative:

- a shuffled-label control runs on the same folds, showing what "no signal"
  looks like for a dataset this small;
- per-fold figures are reported as a median and a range, because 24 clauses split
  into five folds gives roughly five test clauses per fold, and a single fold can
  swing the mean a long way.

Run:  python -m src.evaluation.evaluate_ml
"""

import json
import logging
import os
import pickle

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.svm import LinearSVC

from src.evaluation.benchmark import build_dataset, summarize
from src.models import risk_classifier

logger = logging.getLogger(__name__)

RESULTS_PATH = "data/benchmarks/ml_results.json"
MODEL_PATH = "data/processed/risk_model.pkl"
SHIPPED_MODEL = "logistic_regression"
N_SPLITS = 5
RANDOM_STATE = 42
METRICS = ("accuracy", "precision", "recall", "f1", "roc_auc")


def word_vectorizer():
    """The feature set the shipped model uses."""
    return risk_classifier.build_vectorizer()


def char_vectorizer():
    """Character n-grams.

    Legal wording differs between a compliant and a non-compliant clause by small
    edits ("reflects interest charges only" versus "all-inclusive cost of
    credit"), and character n-grams pick up that kind of local phrasing where word
    unigrams miss it.
    """
    return TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2)


CANDIDATES = {
    "logistic_regression": {
        "vectorizer": word_vectorizer,
        "model": risk_classifier.build_classifier,
        "description": "TF-IDF word 1-2 grams + logistic regression (the shipped model)",
    },
    "linear_svc": {
        "vectorizer": word_vectorizer,
        "model": lambda: LinearSVC(class_weight="balanced"),
        "description": "TF-IDF word 1-2 grams + linear SVM",
    },
    "logistic_regression_char": {
        "vectorizer": char_vectorizer,
        "model": risk_classifier.build_classifier,
        "description": "TF-IDF character 3-5 grams + logistic regression",
    },
}


def scores_for(model, features):
    """A continuous score per row, whichever way the model exposes it."""
    if hasattr(model, "predict_proba"):
        return model.predict_proba(features)[:, 1]
    # LinearSVC has no probabilities, so distance to the hyperplane is used.
    return model.decision_function(features)


def score_fold(y_true, y_pred, y_score):
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y_true, y_score), 4) if len(set(y_true)) > 1 else None,
    }


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return round((ordered[middle - 1] + ordered[middle]) / 2, 4)


def _summarise_folds(per_fold):
    summary = {}
    for metric in METRICS:
        values = [fold[metric] for fold in per_fold if fold[metric] is not None]
        if not values:
            summary[metric] = None
            continue
        summary[metric] = {
            "median": _median(values),
            "min": min(values),
            "max": max(values),
            "mean": round(sum(values) / len(values), 4),
        }
    return summary


def cross_validate(texts, labels, label_name="true"):
    """Stratified k-fold CV, so the reported score is not one lucky split."""
    folds = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    results = {}

    for name, candidate in CANDIDATES.items():
        per_fold = []
        pooled_true, pooled_pred = [], []

        for train_index, test_index in folds.split(texts, labels):
            vectorizer = candidate["vectorizer"]()
            train_features = vectorizer.fit_transform([texts[i] for i in train_index])
            test_features = vectorizer.transform([texts[i] for i in test_index])

            model = candidate["model"]()
            model.fit(train_features, [labels[i] for i in train_index])

            y_true = [labels[i] for i in test_index]
            y_pred = list(model.predict(test_features))
            per_fold.append(score_fold(y_true, y_pred, scores_for(model, test_features)))
            pooled_true.extend(y_true)
            pooled_pred.extend(y_pred)

        results[name] = {
            "label": label_name,
            "description": candidate["description"],
            "folds": per_fold,
            "summary": _summarise_folds(per_fold),
            "pooled_confusion_matrix": {
                "labels": ["compliant(0)", "loophole(1)"],
                "matrix": confusion_matrix(pooled_true, pooled_pred, labels=[0, 1]).tolist(),
            },
        }

    return results


def shuffled_control(texts, labels, seed=RANDOM_STATE):
    """The same models and folds on shuffled labels.

    This is the floor to read the real figures against: with 24 clauses, a model
    can look respectable or terrible purely by chance.
    """
    import random

    shuffled = list(labels)
    random.Random(seed).shuffle(shuffled)
    results = cross_validate(texts, shuffled, label_name="shuffled")
    return {name: block["summary"] for name, block in results.items()}


def evaluate_held_out(records):
    """Score on the benchmark's own test split, held out from training."""
    train = [record for record in records if record["split"] == "train"]
    test = [record for record in records if record["split"] == "test"]

    results = {"train_size": len(train), "test_size": len(test)}
    if not train or not test:
        return results

    train_texts = [record["clause_text"] for record in train]
    train_labels = [int(record["is_loophole"]) for record in train]
    test_texts = [record["clause_text"] for record in test]
    test_labels = [int(record["is_loophole"]) for record in test]

    for name, candidate in CANDIDATES.items():
        vectorizer = candidate["vectorizer"]()
        train_features = vectorizer.fit_transform(train_texts)
        test_features = vectorizer.transform(test_texts)

        model = candidate["model"]()
        model.fit(train_features, train_labels)
        y_pred = list(model.predict(test_features))

        results[name] = score_fold(test_labels, y_pred, scores_for(model, test_features))
        results[name]["confusion_matrix"] = {
            "labels": ["compliant(0)", "loophole(1)"],
            "matrix": confusion_matrix(test_labels, y_pred, labels=[0, 1]).tolist(),
        }

    return results


def gate_behaviour(model, vectorizer, threshold, texts, labels):
    """How the model behaves as the pipeline's triage gate.

    The pipeline does not use the classifier as a verdict: it uses it to decide
    whether a clause is worth running the agents on. Missing a real loophole
    costs more than sending a compliant clause down the pipeline, so the recall
    of the positive class at the shipped threshold is the number that matters.
    """
    features = vectorizer.transform(texts)
    probabilities = model.predict_proba(features)[:, 1]
    predicted = [int(probability > threshold) for probability in probabilities]

    return {
        "threshold": threshold,
        "flagged_for_red_teaming": sum(predicted),
        "of_total": len(texts),
        "precision": round(precision_score(labels, predicted, zero_division=0), 4),
        "recall": round(recall_score(labels, predicted, zero_division=0), 4),
        "confusion_matrix": {
            "labels": ["compliant(0)", "loophole(1)"],
            "matrix": confusion_matrix(labels, predicted, labels=[0, 1]).tolist(),
        },
    }


def threshold_sweep(model, vectorizer, texts, labels):
    """What the triage gate does at every plausible threshold.

    At the shipped 0.3 the gate flags everything, which makes it decorative. This
    table shows what a stricter threshold would cost in missed loopholes, so the
    trade-off can be chosen deliberately instead of by default.
    """
    features = vectorizer.transform(texts)
    probabilities = model.predict_proba(features)[:, 1]

    sweep = []
    for threshold in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        predicted = [int(probability > threshold) for probability in probabilities]
        sweep.append(
            {
                "threshold": threshold,
                "flagged": sum(predicted),
                "flagged_pct": round(100 * sum(predicted) / len(texts), 1),
                "precision": round(precision_score(labels, predicted, zero_division=0), 4),
                "recall": round(recall_score(labels, predicted, zero_division=0), 4),
            }
        )
    return sweep


def explain(model, vectorizer, top_n=12):
    """Which TF-IDF features push a clause towards each class."""
    feature_names = vectorizer.get_feature_names_out()
    coefficients = model.coef_[0]
    ranked = sorted(zip(feature_names, coefficients), key=lambda pair: pair[1])

    return {
        "pushes_towards_loophole": [
            {"feature": name, "weight": round(float(weight), 4)} for name, weight in reversed(ranked[-top_n:])
        ],
        "pushes_towards_compliant": [
            {"feature": name, "weight": round(float(weight), 4)} for name, weight in ranked[:top_n]
        ],
    }


def fit_final_model(records, name=SHIPPED_MODEL):
    """Fit the shipped model on every labelled clause and persist it."""
    texts = [record["clause_text"] for record in records]
    labels = [int(record["is_loophole"]) for record in records]

    candidate = CANDIDATES[name]
    vectorizer = candidate["vectorizer"]()
    features = vectorizer.fit_transform(texts)
    model = candidate["model"]()
    model.fit(features, labels)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, "wb") as handle:
        pickle.dump({"vectorizer": vectorizer, "classifier": model}, handle)

    return model, vectorizer


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    records = build_dataset()
    texts = [record["clause_text"] for record in records]
    labels = [int(record["is_loophole"]) for record in records]

    model, vectorizer = fit_final_model(records)

    report = {
        "dataset": summarize(records),
        "cross_validation": cross_validate(texts, labels),
        "shuffled_label_control": shuffled_control(texts, labels),
        "held_out_test_split": evaluate_held_out(records),
        "gate_behaviour": gate_behaviour(model, vectorizer, risk_classifier.RED_TEAM_THRESHOLD, texts, labels),
        "gate_threshold_sweep": threshold_sweep(model, vectorizer, texts, labels),
        "explainability": explain(model, vectorizer),
        "shipped_model": {
            "name": SHIPPED_MODEL,
            "description": CANDIDATES[SHIPPED_MODEL]["description"],
            "trained_on": len(records),
        },
        "caveats": [
            "The benchmark holds 24 clauses, so every figure here has a wide confidence interval.",
            "The held-out test split is 3 clauses and is reported only for completeness.",
            "Severity in the dataset summary is derived from a documented topic rule, not annotated.",
        ],
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    _print_report(report)
    print(f"\nWrote {RESULTS_PATH} and retrained {MODEL_PATH}")


def _print_report(report):
    dataset = report["dataset"]
    print(f"\nDataset: {dataset['total_clauses']} clauses "
          f"({dataset['loophole']} loophole / {dataset['compliant']} compliant), "
          f"{dataset['distinct_topics']} topics, {dataset['gold_evidence_pages']} gold evidence pages")
    print(f"Severity: {dataset['severity_distribution']} ({dataset['severity_source']})")

    print(f"\n{N_SPLITS}-fold stratified cross-validation (median over folds, with range):")
    for name, block in report["cross_validation"].items():
        summary = block["summary"]
        print(f"  {name}")
        for metric in ("accuracy", "precision", "recall", "f1", "roc_auc"):
            stats = summary[metric]
            if stats:
                print(f"    {metric:<10} median={stats['median']:.3f}  range={stats['min']:.3f}-{stats['max']:.3f}")
        print(f"    pooled confusion matrix {block['pooled_confusion_matrix']['labels']}: "
              f"{block['pooled_confusion_matrix']['matrix']}")

    print("\nShuffled-label control (what no signal looks like on the same folds):")
    for name, summary in report["shuffled_label_control"].items():
        print(f"  {name:<28} f1 median={summary['f1']['median']:.3f}  auc median={summary['roc_auc']['median']:.3f}")

    gate = report["gate_behaviour"]
    print(f"\nTriage gate at the shipped threshold {gate['threshold']} on all {gate['of_total']} clauses:")
    print(f"  flagged={gate['flagged_for_red_teaming']}  precision={gate['precision']:.3f}  "
          f"recall={gate['recall']:.3f}  matrix={gate['confusion_matrix']['matrix']}")

    print("  threshold sweep (flagged% / precision / recall):")
    for row in report["gate_threshold_sweep"]:
        print(f"    {row['threshold']:.1f} -> {row['flagged_pct']:>5.1f}%  "
              f"prec={row['precision']:.3f}  rec={row['recall']:.3f}")

    held = report["held_out_test_split"]
    print(f"\nHeld-out test split (train={held['train_size']}, test={held['test_size']}):")
    for name in CANDIDATES:
        if name in held:
            block = held[name]
            print(f"  {name:<28} prec={block['precision']:.3f} rec={block['recall']:.3f} f1={block['f1']:.3f}")

    print("\nTop features pushing towards a loophole:")
    for item in report["explainability"]["pushes_towards_loophole"][:8]:
        print(f"  {item['feature']:<28} {item['weight']:+.4f}")


if __name__ == "__main__":
    main()









# """Honest scoring for the clause risk classifier.

# Every number here is measured on the labelled benchmark in ``data/benchmarks``,
# which links each clause to the RBI passage that justifies its label.

# Includes cross-validation with per-fold metrics, a shuffled-label control,
# threshold sweeping for the triage gate, and feature coefficient extraction.
# """

# from pathlib import Path
# import json
# import os
# import pickle
# import random

# from sklearn.feature_extraction.text import TfidfVectorizer
# from sklearn.metrics import (
#     accuracy_score,
#     confusion_matrix,
#     f1_score,
#     precision_score,
#     recall_score,
#     roc_auc_score,
# )
# from sklearn.model_selection import StratifiedKFold
# from sklearn.svm import LinearSVC

# from src.evaluation.benchmark import build_dataset, summarize
# from src.models import risk_classifier

# RESULTS_PATH = Path("data/benchmarks/ml_results.json")
# MODEL_PATH = Path("data/processed/risk_model.pkl")
# SHIPPED_MODEL = "logistic_regression"
# N_SPLITS = 5
# RANDOM_STATE = 42
# METRICS = ("accuracy", "precision", "recall", "f1", "roc_auc")


# def word_vectorizer():
#     return risk_classifier.build_vectorizer()


# def char_vectorizer():
#     return TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2)


# CANDIDATES = {
#     "logistic_regression": {
#         "vectorizer": word_vectorizer,
#         "model": risk_classifier.build_classifier,
#         "description": "TF-IDF word 1-2 grams + logistic regression (shipped model)",
#     },
#     "linear_svc": {
#         "vectorizer": word_vectorizer,
#         "model": lambda: LinearSVC(class_weight="balanced"),
#         "description": "TF-IDF word 1-2 grams + linear SVM",
#     },
#     "logistic_regression_char": {
#         "vectorizer": char_vectorizer,
#         "model": risk_classifier.build_classifier,
#         "description": "TF-IDF character 3-5 grams + logistic regression",
#     },
# }


# def _get_scores(model, features):
#     if hasattr(model, "predict_proba"):
#         return model.predict_proba(features)[:, 1]
#     return model.decision_function(features)


# def score_fold(y_true, y_pred, y_score):
#     return {
#         "accuracy": round(accuracy_score(y_true, y_pred), 4),
#         "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
#         "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
#         "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
#         "roc_auc": round(roc_auc_score(y_true, y_score), 4) if len(set(y_true)) > 1 else None,
#     }


# def _median(values):
#     ordered = sorted(values)
#     mid = len(ordered) // 2
#     if len(ordered) % 2:
#         return ordered[mid]
#     return round((ordered[mid - 1] + ordered[mid]) / 2, 4)


# def _summarize_folds(per_fold):
#     summary = {}
#     for m in METRICS:
#         vals = [f[m] for f in per_fold if f[m] is not None]
#         if not vals:
#             summary[m] = None
#             continue
#         summary[m] = {
#             "median": _median(vals),
#             "min": min(vals),
#             "max": max(vals),
#             "mean": round(sum(vals) / len(vals), 4),
#         }
#     return summary


# def cross_validate(texts, labels, label_mode="true"):
#     folds = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
#     results = {}

#     for name, candidate in CANDIDATES.items():
#         per_fold = []
#         p_true, p_pred = [], []

#         for train_idx, test_idx in folds.split(texts, labels):
#             vec = candidate["vectorizer"]()
#             x_train = vec.fit_transform([texts[i] for i in train_idx])
#             x_test = vec.transform([texts[i] for i in test_idx])

#             clf = candidate["model"]()
#             clf.fit(x_train, [labels[i] for i in train_idx])

#             y_t = [labels[i] for i in test_idx]
#             y_p = list(clf.predict(x_test))
            
#             per_fold.append(score_fold(y_t, y_p, _get_scores(clf, x_test)))
#             p_true.extend(y_t)
#             p_pred.extend(y_p)

#         results[name] = {
#             "label": label_mode,
#             "description": candidate["description"],
#             "folds": per_fold,
#             "summary": _summarize_folds(per_fold),
#             "pooled_confusion_matrix": {
#                 "labels": ["compliant(0)", "loophole(1)"],
#                 "matrix": confusion_matrix(p_true, p_pred, labels=[0, 1]).tolist(),
#             },
#         }

#     return results


# def shuffled_control(texts, labels, seed=RANDOM_STATE):
#     shuffled_labels = list(labels)
#     random.Random(seed).shuffle(shuffled_labels)
#     results = cross_validate(texts, shuffled_labels, label_mode="shuffled")
#     return {name: block["summary"] for name, block in results.items()}


# def evaluate_held_out(records):
#     train = [r for r in records if r["split"] == "train"]
#     test = [r for r in records if r["split"] == "test"]

#     results = {"train_size": len(train), "test_size": len(test)}
#     if not train or not test:
#         return results

#     train_texts = [r["clause_text"] for r in train]
#     train_labels = [int(r["is_loophole"]) for r in train]
#     test_texts = [r["clause_text"] for r in test]
#     test_labels = [int(r["is_loophole"]) for r in test]

#     for name, candidate in CANDIDATES.items():
#         vec = candidate["vectorizer"]()
#         x_train = vec.fit_transform(train_texts)
#         x_test = vec.transform(test_texts)

#         clf = candidate["model"]()
#         clf.fit(x_train, train_labels)
#         preds = list(clf.predict(x_test))

#         results[name] = score_fold(test_labels, preds, _get_scores(clf, x_test))
#         results[name]["confusion_matrix"] = {
#             "labels": ["compliant(0)", "loophole(1)"],
#             "matrix": confusion_matrix(test_labels, preds, labels=[0, 1]).tolist(),
#         }

#     return results


# def gate_behaviour(model, vectorizer, threshold, texts, labels):
#     features = vectorizer.transform(texts)
#     probs = model.predict_proba(features)[:, 1]
#     preds = [int(p > threshold) for p in probs]

#     return {
#         "threshold": threshold,
#         "flagged_for_red_teaming": sum(preds),
#         "of_total": len(texts),
#         "precision": round(precision_score(labels, preds, zero_division=0), 4),
#         "recall": round(recall_score(labels, preds, zero_division=0), 4),
#         "confusion_matrix": {
#             "labels": ["compliant(0)", "loophole(1)"],
#             "matrix": confusion_matrix(labels, preds, labels=[0, 1]).tolist(),
#         },
#     }


# def threshold_sweep(model, vectorizer, texts, labels):
#     features = vectorizer.transform(texts)
#     probs = model.predict_proba(features)[:, 1]

#     sweep = []
#     for th in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
#         preds = [int(p > th) for p in probs]
#         sweep.append(
#             {
#                 "threshold": th,
#                 "flagged": sum(preds),
#                 "flagged_pct": round(100 * sum(preds) / len(texts), 1),
#                 "precision": round(precision_score(labels, preds, zero_division=0), 4),
#                 "recall": round(recall_score(labels, preds, zero_division=0), 4),
#             }
#         )
#     return sweep


# def explain(model, vectorizer, top_n=12):
#     features = vectorizer.get_feature_names_out()
#     coefs = model.coef_[0]
#     ranked = sorted(zip(features, coefs), key=lambda x: x[1])

#     return {
#         "pushes_towards_loophole": [
#             {"feature": name, "weight": round(float(w), 4)} for name, w in reversed(ranked[-top_n:])
#         ],
#         "pushes_towards_compliant": [
#             {"feature": name, "weight": round(float(w), 4)} for name, w in ranked[:top_n]
#         ],
#     }


# def fit_final_model(records, name=SHIPPED_MODEL):
#     texts = [r["clause_text"] for r in records]
#     labels = [int(r["is_loophole"]) for r in records]

#     candidate = CANDIDATES[name]
#     vec = candidate["vectorizer"]()
#     features = vec.fit_transform(texts)
    
#     clf = candidate["model"]()
#     clf.fit(features, labels)

#     MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
#     with open(MODEL_PATH, "wb") as f:
#         pickle.dump({"vectorizer": vec, "classifier": clf}, f)

#     return clf, vec


# def main():
#     print("Running evaluation suite...")
#     records = build_dataset()
#     texts = [r["clause_text"] for r in records]
#     labels = [int(r["is_loophole"]) for r in records]

#     model, vectorizer = fit_final_model(records)

#     report = {
#         "dataset": summarize(records),
#         "cross_validation": cross_validate(texts, labels),
#         "shuffled_label_control": shuffled_control(texts, labels),
#         "held_out_test_split": evaluate_held_out(records),
#         "gate_behaviour": gate_behaviour(model, vectorizer, risk_classifier.RED_TEAM_THRESHOLD, texts, labels),
#         "gate_threshold_sweep": threshold_sweep(model, vectorizer, texts, labels),
#         "explainability": explain(model, vectorizer),
#         "shipped_model": {
#             "name": SHIPPED_MODEL,
#             "description": CANDIDATES[SHIPPED_MODEL]["description"],
#             "trained_on": len(records),
#         },
#         "caveats": [
#             "The benchmark holds 24 clauses, so every figure has a wide confidence interval.",
#             "The held-out test split is 3 clauses and is reported only for completeness.",
#             "Severity in dataset summary is derived from topic rules, not manual annotation.",
#         ],
#     }

#     RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
#     with open(RESULTS_PATH, "w", encoding="utf-8") as f:
#         json.dump(report, f, indent=2)

#     _print_report(report)
#     print(f"\nSuccessfully wrote {RESULTS_PATH} and updated model artifact at {MODEL_PATH}")


# def _print_report(report):
#     ds = report["dataset"]
#     print(f"\nDataset: {ds['total_clauses']} clauses "
#           f"({ds['loophole']} loophole / {ds['compliant']} compliant), "
#           f"{ds['distinct_topics']} topics, {ds['gold_evidence_pages']} gold evidence pages")
    
#     print(f"\n{N_SPLITS}-fold stratified cross-validation (median & range):")
#     for name, block in report["cross_validation"].items():
#         summary = block["summary"]
#         print(f"  {name}")
#         for m in METRICS:
#             stats = summary[m]
#             if stats:
#                 print(f"    {m:<10} median={stats['median']:.3f}  range={stats['min']:.3f}-{stats['max']:.3f}")

#     print("\nTop features driving loophole classification:")
#     for item in report["explainability"]["pushes_towards_loophole"][:8]:
#         print(f"  {item['feature']:<28} {item['weight']:+.4f}")


# if __name__ == "__main__":
#     main()