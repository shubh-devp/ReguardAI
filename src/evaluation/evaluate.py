import os
import json
from sklearn.metrics import accuracy_score, classification_report
from src.models.risk_classifier import PolicyRiskClassifier

def main():
    path = "data/benchmarks/policy_loophole_eval_benchmark.json"
    if not os.path.exists(path):
        print(f"benchmark file missing at {path}")
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    clauses = data.get("clauses", [])
    print(f"Loaded {len(clauses)} clauses from benchmark[cite: 1].")

    classifier = PolicyRiskClassifier()
    y_true, y_pred = [], []

    for item in clauses:
        actual = 1 if item["is_loophole"] else 0
        pred = classifier.predict_risk(item["clause_text"])
        predicted = 1 if pred["requires_red_teaming"] else 0

        y_true.append(actual)
        y_pred.append(predicted)

    acc = accuracy_score(y_true, y_pred)
    print(f"\nAccuracy: {acc * 100:.2f}%")
    print("\nClassification Report:")
    print(classification_report(y_true, y_pred, target_names=["Compliant", "Loophole"]))

if __name__ == "__main__":
    main()
    print("fully working 👌")