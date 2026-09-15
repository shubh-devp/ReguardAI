import os
import json
from sklearn.metrics import f1_score, precision_recall_fscore_support
from src.models.risk_classifier import PolicyRiskClassifier
from src.retrieval.hybrid_retriever import load_chunks_from_json, build_chroma_hybrid_retriever
from src.agents.verifier import verify_evidence
from src.agents.retest import ReTestAgent

# Benchmark evaluation dataset with ground truth labels and expected statutory keywords
BENCHMARK_DATASET = [
    {
        "clause_text": "The lender shall levy a penal charge of 2% per month on delayed repayments.",
        "true_label": 1,  # 1 = Loophole / High-Medium Risk
        "expected_keyword": "penal charges"
    },
    {
        "clause_text": "Borrowers can access their Key Fact Statement anytime through the mobile application dashboard.",
        "true_label": 0,  # 0 = Compliant
        "expected_keyword": "Key Fact Statement"
    },
    {
        "clause_text": "Interest shall be compounded monthly on all overdue principal and penal charges.",
        "true_label": 1,
        "expected_keyword": "capitalized"
    },
    {
        "clause_text": "Prepayment charges of 2% shall apply if the loan is foreclosed within the first six months.",
        "true_label": 1,
        "expected_keyword": "foreclosure"
    },
    {
        "clause_text": "The annual percentage rate (APR) along with all fees is explicitly disclosed in the initial sanction letter.",
        "true_label": 0,
        "expected_keyword": "apr"
    }
]

def run_evaluation_harness():
    print("==================================================")
    print("⚖️ Reguard AI - Unified Evaluation Harness")
    print("==================================================")
    
    # Initialize components
    classifier = PolicyRiskClassifier()
    
    print("\n🔍 Initializing Hybrid Retriever for Evaluation...")
    docs = load_chunks_from_json()
    retriever = build_chroma_hybrid_retriever(docs)
    
    retest_agent = ReTestAgent()
    
    y_true = []
    y_pred = []
    retrieval_hits = 0
    verification_successes = 0
    asr_reductions = []
    
    print(f"\nRunning evaluation across {len(BENCHMARK_DATASET)} benchmark clauses...\n")
    
    for idx, item in enumerate(BENCHMARK_DATASET, 1):
        clause = item["clause_text"]
        true_lbl = item["true_label"]
        keyword = item["expected_keyword"]
        
        print(f"[{idx}/{len(BENCHMARK_DATASET)}] Evaluating Clause: \"{clause[:50]}...\"")
        
        # 1. Classifier Evaluation
        risk_res = classifier.predict_risk(clause)
        # Map risk categories to binary labels for F1 (Medium/High Risk = 1, Low Risk = 0)
        pred_lbl = 1 if risk_res["risk_score"] > 0.3 else 0
        y_true.append(true_lbl)
        y_pred.append(pred_lbl)
        
        # 2. Retrieval Evaluation using hybrid retriever invoke()
        raw_docs = retriever.invoke(clause)
        retrieved_docs = [{"text": doc.page_content, "metadata": doc.metadata} for doc in raw_docs[:2]]
        top_passage = retrieved_docs[0]["text"] if retrieved_docs else ""
        
        hit = any(keyword.lower() in doc["text"].lower() for doc in retrieved_docs)
        if hit:
            retrieval_hits += 1
            
        # 3. Evidence Verification & Re-Test (only for clauses flagged as risky)
        if pred_lbl == 1:
            audit_dummy = {
                "violation_confirmed": True,
                "explanation": f"Triggers risk score {risk_res['risk_score']}."
            }
            # Verify evidence
            ver_res = verify_evidence(clause, audit_dummy, top_passage)
            if ver_res.get("is_supported", False):
                verification_successes += 1
                
            # Simulate a compliant rewrite for ASR re-test evaluation
            compliant_rewrite = f"The lender shall comply with statutory guidelines regarding {keyword} without capitalization."
            retest_res = retest_agent.evaluate_patch(clause, compliant_rewrite)
            asr_reductions.append(retest_res["risk_reduction_delta"])

    # Compute Aggregate Metrics
    f1 = f1_score(y_true, y_pred, zero_division=0)
    precision, recall, _, _ = precision_recall_fscore_support(y_true, y_pred, average='binary', zero_division=0)
    retrieval_hit_rate = (retrieval_hits / len(BENCHMARK_DATASET)) * 100
    avg_asr_reduction = (sum(asr_reductions) / len(asr_reductions)) if asr_reductions else 0.0
    flagged_count = sum(y_pred)

    print("\n" + "="*50)
    print("📊 FINAL BENCHMARK EVALUATION REPORT")
    print("="*50)
    print(f"• Classifier Precision   : {precision:.2f}")
    print(f"• Classifier Recall      : {recall:.2f}")
    print(f"• Classifier F1-Score    : {f1:.2f}")
    print(f"• Retrieval Hit Rate     : {retrieval_hit_rate:.1f}%")
    print(f"• Evidence Support Rate  : {(verification_successes / max(1, flagged_count)) * 100:.1f}%")
    print(f"• Avg. ASR Risk Reduction: {avg_asr_reduction:+.4f}")
    print("="*50)
    print("✅ Evaluation harness completed successfully.")

if __name__ == "__main__":
    run_evaluation_harness()