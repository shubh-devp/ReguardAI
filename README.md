# Reguard AI

### Autonomous Multi-Agent Regulatory Compliance Red-Teaming Engine for Digital Lending

Reguard AI takes a lending policy clause, attacks it the way a borrower or an
unscrupulous lender would, retrieves the RBI regulation that decides whether the
attack works, verifies that the cited regulation actually supports the finding,
drafts a compliant rewrite, and then re-runs the same attacks against the rewrite
to measure whether the fix worked.

It is built as an AIML portfolio project. Everything measured in this README comes
from running the code in this repository, including the results that are negative.

---

## What actually happens to a clause

```text
clause
  │
  ▼
1. Risk triage        TF-IDF + logistic regression. Cheap gate: is this worth
                      spending model calls on?
  │
  ▼
2. Red team           4 specialised attackers (disclosure, charges, cooling-off,
                      data/consent) run in parallel, each with its own prompt and
                      lens. Their verdicts are aggregated into an agreement
                      summary, and disagreement is reported, not smoothed over.
  │
  ▼
3. Retriever          BM25 + Chroma dense search fused with weighted reciprocal
                      rank fusion (0.4 / 0.6), filtered to regulatory chunks only.
  │
  ▼
4. Auditor            Judges the clause against the retrieved passage.
  │
  ▼
5. Evidence verifier  Does the passage actually support the finding? Fails closed.
  │
  ▼
6. Remediator         Rewrites the clause, preserving the business intent.
  │
  ▼
7. Re-test            Replays the same attack set against the rewrite. Reports
                      ASR before / after, remediation success rate, and a verdict
                      (fully / partially / not mitigated).
```

Every finding is stored in SQLite with the citation it rested on: document, page,
curated passage id, section, and the runner-up candidates that were considered.

---

## The problem it is aimed at

A lending policy can look reasonable to the business and still breach RBI's
digital lending directions. Reading every clause against hundreds of pages of
regulation by hand is slow, and a single LLM prompt ("is this compliant?") has
its own failure modes: it hallucinates citations, misses regulations, reasons from
one perspective, and produces generic advice.

Reguard AI structures the task instead. The adversarial framing is the point: the
question is not "does this look compliant" but "can I find a concrete scenario in
which a borrower is harmed by this clause, and does a specific RBI paragraph
forbid it".

---

## The agents

All four attackers run concurrently, so the red-team stage costs roughly the
slowest single agent rather than the sum of all four.

| Agent | Job | Module |
|---|---|---|
| Risk triage | Gate on whether to red-team at all | [risk_classifier.py](file:///c:/Users/SHUBH/java/AIML_projects/reguard-ai/src/models/risk_classifier.py) |
| Red team (×4) | One attacker per compliance surface | [challenger.py](file:///c:/Users/SHUBH/java/AIML_projects/reguard-ai/src/agents/challenger.py) |
| Auditor | Judge clause against retrieved regulation | [auditor.py](file:///c:/Users/SHUBH/java/AIML_projects/reguard-ai/src/agents/auditor.py) |
| Evidence verifier | Fail-closed check on the citation | [verifier.py](file:///c:/Users/SHUBH/java/AIML_projects/reguard-ai/src/agents/verifier.py) |
| Remediator | Rewrite preserving business intent | [remediator.py](file:///c:/Users/SHUBH/java/AIML_projects/reguard-ai/src/agents/remediator.py) |
| Re-test | ASR before / after over the same attacks | [retest.py](file:///c:/Users/SHUBH/java/AIML_projects/reguard-ai/src/agents/retest.py) |
| Orchestrator | Wires them together and writes the audit trail | [orchestrator.py](file:///c:/Users/SHUBH/java/AIML_projects/reguard-ai/src/agents/orchestrator.py) |

### Why the red team is four agents and not one

The earlier version of this project ran a single attacker and then had the Re-Test
stage rephrase that one scenario three times, calling the result an attack set.
All three probes came from the same idea, which overstates coverage. The current
version has four attackers with different lenses, and their disagreement is a
first-class output:

- `unanimous_vulnerable` — every surface found an attack
- `unanimous_clear` — every surface judged the clause clear
- `split` — they disagreed, which is exactly the case a reviewer should look at

An attacker that errors is recorded as `failed`, not as `clear`. A surface that
never returned a verdict has not cleared the clause.

---

## Retrieval

Two corpora, joined on `(document, page)`:

- `data/corpus/parsed_corpus_chunks.json` — 1268 mechanically split chunks. This is
  what retrieval searches. A chunk only knows a filename and a page.
- `data/corpus/regulatory_corpus.json` — 57 hand-reviewed passages, each with a
  passage id, section, regulation, effective date and status.

The join in [provenance.py](file:///c:/Users/SHUBH/java/AIML_projects/reguard-ai/src/retrieval/provenance.py)
is what lets a finding cite `RBI-PENAL-0004 · Para 3(ii)` rather than just a
filename, and it is also how the retrieval evaluation knows which page a clause
*should* have returned. All 57 curated pages resolve against the index.

Retrieval is **BM25 + Chroma dense**, fused by weighted reciprocal rank fusion with
weights `[0.4, 0.6]`, and filtered with a Chroma `where` clause so a lender policy
chunk can never be returned as if it were RBI regulation.

Embeddings run on **ONNX Runtime**, not PyTorch. It is the same
`all-MiniLM-L6-v2` weights; the ONNX build needs `onnxruntime` instead of `torch`,
which on a 512 MB instance is the difference between an audit finishing and the
process being killed. Measured on this machine, the switch removed `torch`,
`transformers` and `sentence-transformers` from the import graph entirely and took
the audit from 57 s to 9.9 s.

The vector index is committed and fingerprinted. If the corpus, the chunk schema or
the embedding backend changes, the fingerprint check invalidates the saved index and
rebuilds it, so retrieval can never run against stale vectors.

### Temporal awareness

Every finding carries the effective date and lifecycle status of the passage behind
it, plus a warning when a newer passage of the same regulation exists
([temporal.py](file:///c:/Users/SHUBH/java/AIML_projects/reguard-ai/src/retrieval/temporal.py)).
A missing effective date is common in the corpus and is only a warning. A passage
whose status is not active, or that has been superseded, blocks remediation
entirely: a confident finding grounded in a rule that no longer applies is worse
than no finding.

---

## Evaluation

### Benchmark

`data/benchmarks/policy_loophole_eval_benchmark.json` — 24 hand-labelled clauses
(12 compliant, 12 containing a known loophole) across 10 regulatory topics, built
from real lending policies. Gold evidence resolves to 36 pages across 2 curated RBI
documents.

Severity in the dataset summary is **derived from a documented topic rule**, not
annotated. That is stated in the results file because it matters: a derived label
cannot be used to claim a severity classifier was validated.

### Retrieval — BM25 vs dense vs hybrid

24 clauses, gold evidence at page level, comparing all four strategies on identical
queries and cutoffs:

| Strategy | Recall@4 | Recall@8 | MRR | nDCG@8 |
|---|---|---|---|---|
| BM25 (lexical only) | 0.708 | 0.750 | 0.658 | 0.666 |
| Dense (MiniLM only) | 0.812 | 0.917 | 0.719 | 0.752 |
| **Hybrid (shipped)** | 0.750 | **0.938** | **0.716** | **0.758** |
| Hybrid + lexical rerank | 0.812 | 0.896 | 0.680 | 0.710 |

The hybrid blend beats BM25 on every metric, which is the claim the architecture
rests on. It beats dense on nDCG@8 and Recall@8 but not on Recall@4 or MRR — a
narrower win than "hybrid is strictly better", and worth stating plainly.

**A lexical reranker was measured and did not help** (nDCG@8 0.758 → 0.710), so it
is not in the pipeline. This is a negative result that is kept in the repository
rather than quietly dropped.

### Risk triage — cross-validated, with a shuffled-label control

5-fold stratified cross-validation, median across folds:

| Model | F1 | ROC-AUC |
|---|---|---|
| Logistic regression (shipped) | 0.400 | 0.500 |
| Linear SVM | 0.400 | 0.500 |
| Logistic regression on char n-grams | 0.500 | 0.667 |

| Control | F1 |
|---|---|
| Shuffled labels — logistic regression | 0.500 |
| Shuffled labels — linear SVM | 0.500 |
| **Real labels — logistic regression (shipped)** | **0.400** |

The shipped model scores **no better than the same model trained on randomly
shuffled labels** on a 24-clause benchmark. That is the honest reading: at this
dataset size the TF-IDF triage model has not been shown to learn anything useful
about whether a clause contains a loophole.

What it does do is act as a **gate**. At the shipped threshold of 0.3 it flags
24 of 24 clauses for red-teaming (precision 0.50, recall 1.00), so nothing is
skipped — the red team and the verifier are what actually decide whether a finding
is real. The triage model's job in this architecture is to save model calls on
obviously clean clauses, and at this threshold it currently does not save any.

### Attack success rate and remediation

ASR is measured over the **same attack set before and after the patch**, so the
comparison is like for like. An attack only counts if the Auditor confirms a
violation *and* the verifier accepts the passage behind it, so an unsupported
finding cannot inflate the number.

```text
ASR before = attacks that defeated the original clause / total attacks
ASR after  = attacks that defeated the patched clause  / total attacks
remediation success rate = (defeated before − defeated after) / defeated before
```

The verdict distinguishes the cases the previous implementation conflated:

| Verdict | Meaning |
|---|---|
| `not_measured` | No attack could be measured — nothing is claimed |
| `no_vulnerability_detected` | Nothing defeated the original, so no fix has been demonstrated |
| `fully_mitigated` | Every attack that worked is now blocked |
| `partially_mitigated` | Fewer attacks work, but not none |
| `not_mitigated` | The patch did not reduce the attack surface |

Only `fully_mitigated` counts as a pass, and only when every attack was actually
measured. Previously a partial reduction counted as a pass, and so did a clause
that was never vulnerable.

**A failed model call is not a blocked attack.** If the auditor or the verifier
errors out — a rate limit, a timeout, a malformed reply — that attack returns
"unknown" rather than "failed", is excluded from both rates, and is reported as
`unmeasured_attacks`. Counting it as blocked would have made a patch look like it
worked precisely when the pipeline was broken. This was found by running an audit
straight into the Gemini free-tier rate limit and noticing the ASR had dropped to
zero for the wrong reason.

---

## What an audit costs

One audit is **11 model calls**, counted by instrumenting the client:

| Stage | Calls |
|---|---|
| Red team | 4 (parallel) |
| Auditor + verifier | 2 |
| Remediator | 1 |
| Re-test | 4 (2 clauses × batched auditor + batched verifier, parallel) |

Judging each attack with its own Auditor and Verifier call cost sixteen calls in the
re-test alone — more than the Gemini free tier's 15 requests per minute, so most of
the re-test came back unmeasured. The re-test now judges a whole attack set in one
Auditor call and one Verifier call per clause. Measured effect:

|  | Per-attack calls | Batched |
|---|---|---|
| Model calls per audit | 23 | **11** |
| Wall clock | 79 s | **40 s** |
| Attacks measured | most, rate-limited | all |

Judging is batched; **retrieval is not**. Retrieval is a local search that costs no
model calls, so every attack still gets the passage for its own surface — the same
passage the single-attack path would have used — and each verdict rests on evidence
that is actually about it.

Batching the retrieval as well was tried first and reverted. It is a correctness bug,
not a quality preference:

| Same clause, same patch | One shared passage | Per-attack passages |
|---|---|---|
| ASR before | 0.25 | **1.00** |
| ASR after | 0.25 | 0.25 |
| Verdict | `not_mitigated` | **`partially_mitigated`** |

With one shared passage, three of the four attacks were judged against a
penal-charges passage that says nothing about disclosure, cooling-off or consent.
They came back "not confirmed", so ASR-before collapsed from 1.00 to 0.25 and the run
concluded the patch had fixed nothing — when it had actually closed three of the four
attacks. A red-teaming tool that under-reports is failing in the dangerous direction.

What batching does change is independence: attacks judged in one reply are less
independent than four separate calls, and one malformed reply can affect several
verdicts at once. The reply is indexed for exactly that reason, and anything the
model does not answer is left unmeasured rather than defaulted to "blocked".

On the Gemini free tier a run can still throttle under repeated use. When it does,
the affected attacks are reported as `unmeasured`, the re-test is not marked passed,
and no result is invented.

---

## Known limitations

These are real and should be stated before they are found:

1. **The ML triage model has no measurable signal.** ROC-AUC 0.500 with a
   shuffled-label control scoring the same F1. It is a gate, not a detector.
2. **The benchmark is 24 clauses.** Every figure above has a wide confidence
   interval. The held-out test split is 3 clauses and is reported only for
   completeness, not as evidence.
3. **Retrieval relevance is page-level.** Any chunk from a gold page counts as
   relevant, so the scores are an upper bound on true passage-level accuracy.
4. **Gold evidence coverage is partial.** It exists only for clauses whose cited
   passages come from the two curated RBI documents.
5. **ASR is measured against LLM-judged attacks.** Both the attacks and the
   success judgements come from the same model family. This is a benchmark of the
   pipeline's internal consistency, not an independent security guarantee.
6. **The red team covers 4 compliance surfaces.** RBI's directions cover more.
7. **Temporal coverage depends on the corpus.** Most curated passages have no
   effective date recorded, so most findings report "unknown" rather than a date.
   The supersession check is implemented and tested, but on this corpus it only
   fires for the passages that are actually dated.
8. **The rate limiter is in-process.** On a single Render instance that is
   sufficient; it would not survive horizontal scaling.
9. **An audit needs 11 model calls**, and the re-test is 4 of them. On the Gemini
   free tier a burst of audits can still throttle. The pipeline degrades safely —
   unmeasured attacks are reported as unmeasured and the re-test is not marked
   passed — but a throttled audit produces less information, not a wrong answer.

---

## API

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Service status and endpoint list |
| `/api/health` | GET | Cheap liveness check. Does not touch the models. |
| `/api/ready` | GET | Checks the corpus, ONNX model and index. Returns 503 when retrieval is not usable. |
| `/api/metrics` | GET | The measured evaluation results the dashboard displays |
| `/api/audit` | POST | Runs the whole pipeline for one clause |

`POST /api/audit` body:

```json
{
  "policy_name": "Digital_Lending_Policy.txt",
  "clause_text": "The lender shall levy a penal charge of 2% per month...",
  "full_text": "optional; defaults to clause_text"
}
```

Every response carries an `X-Request-Id` header, and errors carry a machine-readable
`code` alongside the human-readable `error` message:

```json
{ "error": "clause_text is required.", "code": "invalid_request", "request_id": "a1b2c3d4e5f6" }
```

Bodies are capped at 64 KB and `/api/audit` is rate limited per caller (default
30 requests per 60 s, configurable through `RATE_LIMIT_REQUESTS` and
`RATE_LIMIT_WINDOW_SECONDS`).

`/api/ready` exists because of a failure this project actually hit: a deployment
with no corpus and no index that answered `200` to every request while every
finding quietly cited the same hardcoded fallback sentence. The port being open
says nothing about whether retrieval works.

---

## Project structure

```text
reguard-ai/
├── data/
│   ├── benchmarks/                 # Labelled benchmark + written evaluation results
│   │   ├── policy_loophole_eval_benchmark.json
│   │   ├── ml_results.json         # Written by evaluate_ml.py
│   │   └── retrieval_results.json  # Written by evaluate_retrieval.py
│   ├── chroma_db/                  # Prebuilt vector index + corpus fingerprint
│   ├── corpus/                     # Parsed chunks + 57 curated passages
│   ├── models/onnx_models/         # all-MiniLM-L6-v2 in ONNX form
│   ├── policies/                   # Source lending policies used to build the benchmark
│   └── regulatory/                 # The RBI PDFs
├── frontend/                       # React + Vite + Tailwind single-page UI
│   └── src/
│       ├── App.jsx                 # Page shell
│       ├── api/audit.js            # POST /api/audit client
│       ├── api/metrics.js          # GET /api/metrics client
│       ├── lib/format.js           # Display helpers and status wording
│       └── components/
│           ├── AuditForm.jsx
│           ├── AuditResults.jsx    # Red team table, evidence, ASR before/after
│           └── ModelMetrics.jsx    # Retrieval and ML scores from /api/metrics
├── src/
│   ├── agents/                     # llm, challenger, auditor, verifier,
│   │                               # remediator, retest, orchestrator
│   ├── api/app.py                  # Flask API
│   ├── database/sql_manager.py     # SQLite schema, migrations, inserts
│   ├── evaluation/
│   │   ├── benchmark.py            # Loads the benchmark, resolves gold evidence
│   │   ├── evaluate_ml.py          # Cross-validation, shuffled control, gate sweep
│   │   ├── evaluate_retrieval.py   # Recall@K / MRR / nDCG@K per strategy
│   │   └── results.py              # Serves the result files to the dashboard
│   ├── ingestion/parser.py         # Builds corpus chunks from the RBI PDFs
│   ├── models/risk_classifier.py   # TF-IDF + logistic regression triage
│   ├── retrieval/
│   │   ├── hybrid_retriever.py     # BM25 + Chroma ensemble, ONNX embeddings
│   │   ├── provenance.py           # Joins chunks to reviewed passages
│   │   └── temporal.py             # Effective dates, status, supersession
│   └── cli.py                      # Batch file auditing
├── tests/                          # 122 pytest cases, no network required
├── Procfile
├── .env.example
└── requirements.txt
```

---

## Running locally

```bash
# Backend
python -m venv venv
venv\Scripts\activate                 # source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
copy .env.example .env                # then paste your GEMINI_API_KEY into .env
python -m src.api.app                 # http://localhost:5000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                           # http://localhost:5173
```

Check the backend is fully up (not just listening):

```bash
curl http://localhost:5000/api/health
curl http://localhost:5000/api/ready
```

---

## Reproducing the numbers in this README

```bash
# All tests
python -m pytest tests -q

# Retrieval: Recall@K, MRR and nDCG@K for bm25 / dense / hybrid / hybrid+rerank
python -m src.evaluation.evaluate_retrieval

# Risk triage: 5-fold CV per candidate, shuffled-label control, gate sweep
python -m src.evaluation.evaluate_ml
```

Both scripts write their results into `data/benchmarks/`, and `/api/metrics`
serves those same files to the dashboard, so the README and the UI cannot drift
apart.

---

## Deployment (Render)

**Backend — Web Service**

| Setting | Value |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Start command | `python -m src.api.app` (also in the `Procfile`) |
| Environment | `GEMINI_API_KEY`, `PYTHON_VERSION` = `3.12.7`, `ALLOWED_ORIGINS` |

**Frontend — Static Site**

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm install && npm run build` |
| Publish directory | `dist` |
| Environment | `VITE_API_URL` = `https://<your-backend>.onrender.com/api/audit` |

Things worth knowing before a demo:

- The ONNX model file and the Chroma index are committed. A deployment loads them
  instead of downloading or re-embedding, which is what keeps startup inside the
  512 MB free tier.
- `VITE_API_URL` must include the full `/api/audit` path. Posting to the bare
  origin returns `405` from Flask.
- Warm-up runs in a background thread right after the port opens, so Render's port
  scan passes while the models load.
- The SQLite audit trail is on ephemeral disk, so it resets on every deploy.
- `ALLOWED_ORIGINS` defaults to `*` for local development. Set it to the frontend
  origin in production.

---

## Tech stack

**Backend** — Python, Flask, flask-cors, SQLite, pytest
**Retrieval** — ChromaDB, BM25 (`rank_bm25` via LangChain), ONNX Runtime,
`all-MiniLM-L6-v2`
**ML** — scikit-learn (TF-IDF, logistic regression, linear SVM), NumPy
**LLM** — Google Gemini via `google-genai`
**Frontend** — React 19, Vite, Tailwind CSS v4
**Data** — RBI regulatory PDFs, parsed to JSON, plus a hand-labelled benchmark
