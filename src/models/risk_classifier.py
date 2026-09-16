# """TF-IDF + Logistic Regression clause risk triage.

# This is the gate at the front of the pipeline. It answers one question: is this
# clause worth spending an expensive multi-agent audit on? It is deliberately a
# small, fast, classical model rather than an LLM call, because running it on every
# clause costs nothing.

# It is trained on the labelled benchmark in ``data/benchmarks`` - the same clauses
# the evaluation scores it on, so there is one source of truth for the labels. The
# earlier version trained on eight hand-written sentences copied five times, which
# put identical sentences in both halves of its own train/test split.
# """

# import logging
# import os
# import pickle

# from sklearn.feature_extraction.text import TfidfVectorizer
# from sklearn.linear_model import LogisticRegression

# logger = logging.getLogger(__name__)

# MODEL_PATH = "data/processed/risk_model.pkl"

# # The score above which a clause is sent for red-teaming. Kept at the value the
# # pipeline has always used; the evaluation reports what it costs in precision.
# RED_TEAM_THRESHOLD = 0.3
# HIGH_RISK_THRESHOLD = 0.6


# def build_vectorizer():
#     """The shipped feature extractor."""
#     return TfidfVectorizer(ngram_range=(1, 2), stop_words="english")


# def build_classifier():
#     """The shipped classifier.

#     ``class_weight='balanced'`` keeps the two benchmark labels on equal footing,
#     and ``predict_proba`` gives the calibrated score the gate needs.
#     """
#     return LogisticRegression(class_weight="balanced", max_iter=1000)


# class PolicyRiskClassifier:
#     """Loads the saved model, training it from the benchmark if none exists."""

#     def __init__(self, model_path=MODEL_PATH):
#         self.model_path = model_path
#         self.vectorizer = None
#         self.classifier = None
#         self._load_or_train_model()

#     def _load_or_train_model(self):
#         if os.path.exists(self.model_path):
#             try:
#                 with open(self.model_path, "rb") as handle:
#                     bundle = pickle.load(handle)
#                 self.vectorizer = bundle["vectorizer"]
#                 self.classifier = bundle["classifier"]
#                 return
#             except Exception:
#                 # A stale or unreadable pickle should not stop the service, but it
#                 # should not vanish silently either.
#                 logger.exception("Could not load %s; retraining from the benchmark", self.model_path)

#         self.train()

#     def train(self, records=None):
#         """Fit on the labelled benchmark and persist the model."""
#         if records is None:
#             # Imported here so the module stays importable without the benchmark
#             # present, which keeps the API boot resilient.
#             from src.evaluation.benchmark import build_dataset

#             records = build_dataset()

#         texts = [record["clause_text"] for record in records]
#         labels = [int(record["is_loophole"]) for record in records]

#         self.vectorizer = build_vectorizer()
#         features = self.vectorizer.fit_transform(texts)
#         self.classifier = build_classifier()
#         self.classifier.fit(features, labels)

#         os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
#         with open(self.model_path, "wb") as handle:
#             pickle.dump({"vectorizer": self.vectorizer, "classifier": self.classifier}, handle)

#         logger.info("Risk classifier trained on %d labelled clauses", len(records))
#         return self

#     def predict_risk(self, clause_text: str) -> dict:
#         """Score one clause.

#         Returns the probability the clause carries an exploitable gap, a
#         three-band label for display, and the gate decision the orchestrator uses.
#         """
#         features = self.vectorizer.transform([clause_text])
#         probability = float(self.classifier.predict_proba(features)[0][1])

#         if probability > HIGH_RISK_THRESHOLD:
#             category = "High Risk"
#         elif probability > RED_TEAM_THRESHOLD:
#             category = "Medium Risk"
#         else:
#             category = "Low Risk"

#         return {
#             "risk_score": round(probability, 4),
#             "category": category,
#             "requires_red_teaming": bool(probability > RED_TEAM_THRESHOLD),
#         }


# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO, format="%(message)s")
#     classifier = PolicyRiskClassifier()
#     sample = "The lender shall levy a penal charge of 2% per month on delayed repayments."
#     print(classifier.predict_risk(sample))





"""TF-IDF + Logistic Regression clause risk triage.

Front-end gatekeeper for the analysis pipeline. Evaluates whether a clause
warrants an intensive multi-agent audit. Implemented as a lightweight classical
model to keep per-clause evaluation costs negligible compared to direct LLM usage.

Trained against the benchmark definitions under ``data/benchmarks`` to ensure
consistent ground-truth labels across both training and evaluation phases.
"""

from pathlib import Path
import pickle

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

# Persistence settings and operational thresholds
MODEL_FILE_PATH = Path("data/processed/risk_model.pkl")
RED_TEAM_TRIGGER_THRESHOLD = 0.3
SEVERE_RISK_THRESHOLD = 0.6


def _create_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(ngram_range=(1, 2), stop_words="english")


def _create_model_instance() -> LogisticRegression:
    return LogisticRegression(class_weight="balanced", max_iter=1000)


class PolicyRiskClassifier:
    """Manages model loading, lazy training, and inference for incoming clauses."""

    def __init__(self, model_path: Path = MODEL_FILE_PATH):
        self.model_path = Path(model_path)
        self.vectorizer = None
        self.classifier = None
        self._initialize_model()

    def _initialize_model(self) -> None:
        if self.model_path.exists():
            try:
                with open(self.model_path, "rb") as stream:
                    bundle = pickle.load(stream)
                self.vectorizer = bundle["vectorizer"]
                self.classifier = bundle["classifier"]
                return
            except Exception as e:
                print(f"Failed to load serialized model from {self.model_path} due to {e}; triggering retrain.")

        self.train()

    def train(self, records: list = None) -> "PolicyRiskClassifier":
        """Fits vectorizer and classifier on benchmark data and serializes the artifact."""
        if records is None:
            # Deferred import prevents circular dependencies and boot failures if dataset is missing
            from src.evaluation.benchmark import build_dataset

            records = build_dataset()

        corpus = [item["clause_text"] for item in records]
        targets = [int(item["is_loophole"]) for item in records]

        self.vectorizer = _create_vectorizer()
        matrix = self.vectorizer.fit_transform(corpus)
        
        self.classifier = _create_model_instance()
        self.classifier.fit(matrix, targets)

        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.model_path, "wb") as stream:
            pickle.dump({"vectorizer": self.vectorizer, "classifier": self.classifier}, stream)

        print(f"Successfully trained risk classifier utilizing {len(records)} records.")
        return self

    def predict_risk(self, clause_text: str) -> dict:
        """Evaluates a single clause text snippet.

        Returns structural metrics including vulnerability probability, display tier,
        and orchestrator gate flags.
        """
        vectorized_input = self.vectorizer.transform([clause_text])
        risk_probability = float(self.classifier.predict_proba(vectorized_input)[0][1])

        if risk_probability > SEVERE_RISK_THRESHOLD:
            risk_band = "High Risk"
        elif risk_probability > RED_TEAM_TRIGGER_THRESHOLD:
            risk_band = "Medium Risk"
        else:
            risk_band = "Low Risk"

        return {
            "risk_score": round(risk_probability, 4),
            "category": risk_band,
            "requires_red_teaming": bool(risk_probability > RED_TEAM_TRIGGER_THRESHOLD),
        }


if __name__ == "__main__":
    risk_engine = PolicyRiskClassifier()
    test_snippet = "The lender shall levy a penal charge of 2% per month on delayed repayments."
    print(risk_engine.predict_risk(test_snippet))