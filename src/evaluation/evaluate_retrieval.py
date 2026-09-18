import json
import logging
import time

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.evaluation.benchmark import build_dataset, gold_page_set, summarize
from src.retrieval.hybrid_retriever import load_chunks_from_json, build_retriever

logger = logging.getLogger(__name__)

RESULTS_PATH = "data/benchmarks/retrieval_results.json"
CANDIDATE_K = 8
CUTOFFS = (1, 3, 4, 8)
PRODUCTION_K = 4


def page_of(document):
    return (document.metadata.get("source"), document.metadata.get("page"))


def dedupe_by_page(documents):
    seen = set()
    unique = []
    for document in documents:
        key = page_of(document)
        if key not in seen:
            seen.add(key)
            unique.append(document)
    return unique


def average_precision_at(ranked_pages, gold, k):
    if not gold:
        return None
    return len(set(ranked_pages[:k]) & gold) / len(gold)


def hit_at(ranked_pages, gold, k):
    if not gold:
        return None
    return float(bool(set(ranked_pages[:k]) & gold))


def reciprocal_rank(ranked_pages, gold):
    if not gold:
        return None
    for position, page in enumerate(ranked_pages, start=1):
        if page in gold:
            return 1 / position
    return 0.0


def ndcg_at(ranked_pages, gold, k):
    if not gold:
        return None
    dcg = sum(1 / _log2(position + 1)
              for position, page in enumerate(ranked_pages[:k], start=1) if page in gold)
    ideal = sum(1 / _log2(position + 1) for position in range(1, min(len(gold), k) + 1))
    return dcg / ideal if ideal else 0.0


def _log2(value):
    import math

    return math.log2(value)


def lexical_rerank(query, documents):
    if len(documents) < 2:
        return documents

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform([query] + [document.page_content for document in documents])
    similarity = cosine_similarity(matrix[0:1], matrix[1:]).ravel()
    order = similarity.argsort()[::-1]
    return [documents[index] for index in order]


def evaluate_strategy(name, retriever, records, rerank=False):
    per_clause = []

    for record in records:
        gold = gold_page_set(record)
        if not gold:
            continue

        documents = retriever.invoke(record["clause_text"])
        if rerank:
            documents = lexical_rerank(record["clause_text"], documents)

        ranked_pages = [page_of(document) for document in dedupe_by_page(documents)]

        row = {"clause_id": record["clause_id"], "gold_pages": len(gold)}
        for k in CUTOFFS:
            row[f"recall@{k}"] = average_precision_at(ranked_pages, gold, k)
            row[f"hit@{k}"] = hit_at(ranked_pages, gold, k)
            row[f"ndcg@{k}"] = round(ndcg_at(ranked_pages, gold, k), 4)
        row["mrr"] = round(reciprocal_rank(ranked_pages, gold), 4)
        per_clause.append(row)

    return {"strategy": name, "clauses_scored": len(per_clause), "per_clause": per_clause,
            "macro": _macro_average(per_clause)}


def _macro_average(per_clause):
    if not per_clause:
        return {}

    keys = [key for key in per_clause[0] if key not in ("clause_id", "gold_pages")]
    return {key: round(sum(row[key] for row in per_clause) / len(per_clause), 4) for key in keys}


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    records = build_dataset()
    scored = [record for record in records if gold_page_set(record)]
    documents = load_chunks_from_json()

    print(f"Benchmark: {len(records)} clauses, {len(scored)} with resolved gold evidence")
    print(f"Corpus: {len(documents)} chunks\n")

    strategies = {
        "bm25": {"strategy": "bm25"},
        "dense": {"strategy": "dense"},
        "hybrid": {"strategy": "hybrid"},
    }

    results = {}
    for name, options in strategies.items():
        started = time.time()
        retriever = build_retriever(documents, k=CANDIDATE_K, **options)
        results[name] = evaluate_strategy(name, retriever, scored)
        results[name]["seconds"] = round(time.time() - started, 1)
        print(f"{name:<8} scored in {results[name]['seconds']}s")

    hybrid_retriever = build_retriever(documents, strategy="hybrid", k=CANDIDATE_K)
    results["hybrid_rerank"] = evaluate_strategy("hybrid_rerank", hybrid_retriever, scored, rerank=True)

    report = {
        "dataset": summarize(records),
        "clauses_scored": len(scored),
        "candidate_k": CANDIDATE_K,
        "production_k": PRODUCTION_K,
        "strategies": results,
        "verdict": _verdict(results),
        "caveats": [
            "Gold evidence exists only for clauses whose cited passages come from the "
            "two curated documents, so coverage is partial.",
            "Relevance is page-level: any chunk from a gold page counts as relevant.",
        ],
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    _print_report(report)
    print(f"\nWrote {RESULTS_PATH}")


def _verdict(results):
    hybrid = results["hybrid"]["macro"]
    best = max(results, key=lambda name: results[name]["macro"].get("ndcg@8", 0))

    return {
        "best_ndcg@8": best,
        "hybrid_beats_bm25": hybrid.get("ndcg@8", 0) > results["bm25"]["macro"].get("ndcg@8", 0),
        "hybrid_beats_dense": hybrid.get("ndcg@8", 0) > results["dense"]["macro"].get("ndcg@8", 0),
        "reranking_improves_hybrid": (
            results["hybrid_rerank"]["macro"].get("ndcg@8", 0) > hybrid.get("ndcg@8", 0)
        ),
    }


def _print_report(report):
    print("\nMacro averages over clauses with gold evidence:")
    header = f"{'strategy':<16}" + "".join(f"{f'recall@{k}':>10}" for k in CUTOFFS) + f"{'mrr':>9}" + f"{'ndcg@8':>9}"
    print(header)
    for name, block in report["strategies"].items():
        macro = block["macro"]
        row = f"{name:<16}" + "".join(f"{macro[f'recall@{k}']:>10.3f}" for k in CUTOFFS)
        row += f"{macro['mrr']:>9.3f}" + f"{macro['ndcg@8']:>9.3f}"
        print(row)

    verdict = report["verdict"]
    print(f"\nBest nDCG@8: {verdict['best_ndcg@8']}")
    print(f"Hybrid beats BM25:  {verdict['hybrid_beats_bm25']}")
    print(f"Hybrid beats dense: {verdict['hybrid_beats_dense']}")
    print(f"Reranking improves the hybrid: {verdict['reranking_improves_hybrid']}")


if __name__ == "__main__":
    main()