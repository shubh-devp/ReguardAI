# Reguard AI

### Autonomous Multi-Agent Regulatory Compliance Red-Teaming Engine for Fintech & Digital Lending

> Reguard AI is an AI-powered compliance red-teaming system designed to stress-test digital lending policies against financial regulations, identify potential compliance risks, and generate business-intent-preserving remediation suggestions.

---

## 🚀 Overview

Financial institutions and digital lending platforms operate under complex regulatory requirements. A policy can appear reasonable from a business perspective while still violating one or more regulatory requirements.

**Reguard AI** approaches this problem as a **red-teaming task**.

Instead of simply asking an LLM:

> "Is this policy compliant?"

Reguard AI attempts to actively **attack the policy from multiple compliance perspectives**, retrieve relevant regulatory evidence, identify potential violations, and generate corrective recommendations.

The system focuses specifically on:

- Fintech
- Digital lending
- RBI financial regulations
- Lending policy compliance
- Regulatory risk detection
- Retrieval-Augmented Generation (RAG)
- Multi-agent AI
- Adversarial compliance testing

---

## 🎯 Problem Statement

Traditional compliance workflows often depend heavily on manual review of lengthy regulatory documents.

A digital lending policy may contain rules related to:

- APR disclosure
- Interest and charges
- Cooling-off periods
- Loan disbursal
- Repayment
- Penal charges
- Key Fact Statements
- Data handling
- Customer communication
- Automated decision-making

Manually checking every policy statement against hundreds of pages of regulatory material is:

- Time-consuming
- Difficult to scale
- Prone to human oversight
- Difficult to continuously test

Large Language Models can help with document understanding, but a simple LLM-based compliance checker can suffer from:

- Hallucinations
- Missing relevant regulations
- Weak evidence grounding
- Single-perspective analysis
- Overly generic recommendations

Reguard AI addresses these limitations by combining **retrieval, structured analysis, multiple adversarial agents, and evidence-grounded remediation**.

---

# 🧠 Core Idea

Reguard AI treats a company's lending policy as something that needs to be **red-teamed**.

### Traditional approach

```text
Policy
   ↓
LLM
   ↓
"Compliant / Non-Compliant"



                 ┌─────────────────────┐
                 │   Lending Policy    │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Policy Processing   │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Hybrid RAG Engine   │
                 │ BM25 + Dense Search │
                 └──────────┬──────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │ Regulatory Evidence         │
              │ RBI Lending Directions      │
              └──────────────┬──────────────┘
                             │
                             ▼
              ┌─────────────────────────────┐
              │ Multi-Agent Red Team Layer  │
              └──────────────┬──────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        Disclosure       Disbursal      Cooling-off
         Agent            Agent           Agent
              │              │              │
              └──────────────┼──────────────┘
                             ▼
                  ┌────────────────────┐
                  │ Risk Aggregation    │
                  └──────────┬─────────┘
                             ▼
                  ┌────────────────────┐
                  │ Compliance Report  │
                  └──────────┬─────────┘
                             ▼
                  ┌────────────────────┐
                  │ Remediation Engine │
                  └────────────────────┘

1. Regulatory Document Ingestion

Reguard AI processes regulatory documents and converts them into searchable knowledge.

The ingestion pipeline includes:

Document loading
Text extraction
Cleaning
Chunking
Metadata generation
Embedding generation
Search indexing


2. Hybrid Retrieval-Augmented Generation

Instead of relying exclusively on semantic vector search, Reguard AI combines:

BM25

Useful for exact regulatory terminology, keywords, section numbers, and legal phrases.

Dense Retrieval

Useful for understanding semantic similarity between:

Policy statements
Regulatory clauses
Compliance requirements


User Policy
     │
     ├──────────────► BM25 Search
     │
     └──────────────► Dense Vector Search
                         │
                         ▼
                 Result Fusion
                         │
                         ▼
              Relevant Regulations


This allows the system to retrieve both:

Exact lexical matches
Semantically related regulatory requirements



🤖 Multi-Agent Compliance Red Team

Reguard AI uses multiple specialized agents instead of relying on a single compliance evaluator.

Each agent focuses on a different attack surface.

Example:

                    Policy
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
 Disclosure       Disbursal      Cooling-off
   Agent            Agent          Agent
        │             │             │
        ▼             ▼             ▼
    Findings       Findings       Findings
        │             │             │
        └─────────────┼─────────────┘
                      ▼
              Risk Aggregator




⚔️ Compliance Red-Teaming

The system does not simply search for matching regulations.

Instead, agents attempt to construct adversarial interpretations and scenarios that could expose weaknesses in a policy.

For example:

Policy

"The loan amount is automatically transferred immediately after approval."

The red-team process may ask:

Does this policy account for:
- applicable cooling-off requirements?
- customer communication?
- applicable disbursal conditions?
- regulatory restrictions?

The system then retrieves supporting regulatory evidence and evaluates the policy against it.

📊 Compliance Risk Analysis

Each detected issue can be represented using structured information such as:

Risk
├── Policy Statement
├── Risk Category
├── Severity
├── Regulatory Requirement
├── Evidence
├── Explanation
└── Recommended Remediation

Example:

{
  "category": "Disclosure",
  "severity": "High",
  "policy_statement": "...",
  "risk": "...",
  "regulatory_evidence": "...",
  "recommendation": "..."
}
🛠️ Remediation Engine

Finding a violation is only part of the problem.

Reguard AI also attempts to produce a corrective recommendation.

The objective is:

Original Policy
      ↓
Compliance Risk
      ↓
Relevant Regulation
      ↓
Remediation
      ↓
Updated Policy

The remediation should ideally:

Address the regulatory issue
Preserve the original business intent
Avoid unnecessary policy changes
Reference the relevant regulatory evidence
📉 Attack Success Rate (ASR)

One of the experimental objectives of Reguard AI is to evaluate how effectively different red-team configurations uncover compliance weaknesses.

A useful evaluation metric is:

Attack Success Rate
ASR =
Successful Compliance Attacks
─────────────────────────────
Total Compliance Attacks

The project can compare:

Single-Agent System
        vs
Multi-Agent System

to investigate whether multiple specialized agents are more effective at identifying policy weaknesses.

🧪 Evaluation Strategy

The system can be evaluated using a benchmark containing:

Compliant Policies

Policies designed to satisfy relevant requirements.

Non-Compliant Policies

Policies containing known compliance violations.

Adversarial Policies

Policies where violations are intentionally hidden using:

Ambiguous language
Indirect wording
Business-oriented phrasing
Missing information
Conditional statements
Evaluation Metrics

Potential metrics include:

Precision

How many detected violations are actually valid.

Precision =
True Positives
────────────────────────
True Positives + False Positives
Recall

How many actual violations were detected.

Recall =
True Positives
────────────────────────
True Positives + False Negatives
F1 Score

Balances precision and recall.

F1 =
2 × Precision × Recall
──────────────────────
Precision + Recall
Retrieval Metrics

The RAG pipeline can additionally be evaluated using:

Recall@K
Precision@K
MRR
Retrieval hit rate
Red-Team Metrics
Attack Success Rate
Violation detection rate
False-positive rate
Remediation acceptance rate
🏗️ System Architecture
                         ┌──────────────────┐
                         │   React Frontend │
                         └────────┬─────────┘
                                  │
                                  │ HTTP / REST
                                  ▼
                         ┌──────────────────┐
                         │ FastAPI Backend  │
                         └────────┬─────────┘
                                  │
                   ┌──────────────┼──────────────┐
                   │              │              │
                   ▼              ▼              ▼
              Policy API      RAG Engine      Agent Layer
                   │              │              │
                   │              │        ┌─────┴─────┐
                   │              │        ▼           ▼
                   │              │    Agent 1      Agent 2
                   │              │        │           │
                   │              │        └─────┬─────┘
                   │              │              │
                   │              ▼              │
                   │       Hybrid Retrieval      │
                   │        ┌────────────┐        │
                   │        │ BM25       │        │
                   │        │ Dense      │        │
                   │        └─────┬──────┘        │
                   │              │               │
                   ▼              ▼               ▼
              Database      Vector Store     LLM / API
                   │              │               │
                   └──────────────┼───────────────┘
                                  ▼
                         Compliance Results
                                  │
                                  ▼
                         Remediation Engine
                                  │
                                  ▼
                         Frontend Dashboard
🔄 RAG Pipeline
Regulatory Documents
        │
        ▼
Document Loader
        │
        ▼
Text Extraction
        │
        ▼
Cleaning & Normalization
        │
        ▼
Chunking
        │
        ▼
Metadata
        │
        ├──────────────► BM25 Index
        │
        └──────────────► Embedding Model
                              │
                              ▼
                        Vector Database

During analysis:

Policy
   │
   ▼
Query Generation
   │
   ├──────────────► BM25
   │
   └──────────────► Dense Retrieval
                         │
                         ▼
                    Result Fusion
                         │
                         ▼
                 Regulatory Context
                         │
                         ▼
                    LLM Analysis



🧰 Technology Stack
Frontend:
React
JavaScript
Tailwind CSS
REST API integration

Backend:
Python
FastAPI
REST APIs
AI / ML
Natural Language Processing
Text preprocessing
Embeddings
Semantic similarity
Classification techniques
Machine Learning
Deep Learning
Transformer-based models
Large Language Models
RAG
BM25
Dense Vector Retrieval
Hybrid Search
Chunking
Embeddings
Retrieval-Augmented Generation


Data:
Regulatory documents
Structured compliance benchmark
Policy documents
Metadata
Development
Git
GitHub
Docker
Environment variables


## 📁 Project Structure

```text
reguard-ai/
├── data/
│   ├── chroma_db/                  # ChromaDB vector store directory
│   ├── corpus/                     # Parsed RBI statutory text chunks (JSON)
│   ├── database/                   # SQLite audit trail (reguard_audit.db)
│   └── processed/                  # Serialized ML classifier weights (.pkl)
├── frontend/                       # React + Tailwind single-page UI
│   └── src/
│       ├── App.jsx                 # Page shell: header, form, loading, results
│       ├── api/audit.js            # Backend client (uses VITE_API_URL)
│       └── components/             # AuditForm, AuditResults
├── src/
│   ├── agents/
│   │   ├── llm.py                  # Shared Gemini client, retries, JSON parsing
│   │   ├── analyst.py              # Clause structural parser (standalone)
│   │   ├── challenger.py           # Adversarial red-team attacker agent
│   │   ├── auditor.py              # Regulatory compliance auditor agent
│   │   ├── verifier.py             # Evidence support validator (fail-closed)
│   │   ├── remediator.py           # Policy patch generator agent
│   │   ├── retest.py               # Deterministic ASR re-test agent
│   │   └── orchestrator.py         # End-to-end pipeline orchestrator loop
│   ├── database/
│   │   └── sql_manager.py          # SQLite schema, init, and insert operations
│   ├── ingestion/
│   │   └── parser.py               # Builds corpus chunks from the RBI PDFs
│   ├── models/
│   │   └── risk_classifier.py      # TF-IDF + Logistic Regression triage gatekeeper
│   ├── retrieval/
│   │   └── hybrid_retriever.py     # BM25 + ChromaDB ensemble retriever
│   ├── evaluation/
│   │   ├── evaluate.py             # Classifier / retrieval scoring script
│   │   └── evaluate_pipeline.py    # Benchmark harness for the pipeline
│   ├── cli.py                      # Batch file auditing command-line interface
│   └── api/
│       └── app.py                  # Flask API: POST /api/audit, GET /api/health
├── Procfile                        # Start command used by Render
├── .env.example                    # Template for the environment variables
├── requirements.txt                # Python backend dependencies
└── README.md                       # Project documentation



## 🛠️ Running Locally

```bash
# Backend
python -m venv venv
venv\Scripts\activate                 # Windows  (source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
copy .env.example .env                # then paste your GEMINI_API_KEY into .env
python -m src.api.app                 # http://localhost:5000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                           # http://localhost:5173
```

Quick check that the API is up: `GET http://localhost:5000/api/health`

## 🚀 Deployment (Render)

**Backend — Web Service**

| Setting | Value |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Start command | `python -m src.api.app` (also provided in the `Procfile`) |
| Environment | `GEMINI_API_KEY`, `PYTHON_VERSION` = `3.12.7` |

**Frontend — Static Site**

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm install && npm run build` |
| Publish directory | `dist` |
| Environment | `VITE_API_URL` = `https://<your-backend>.onrender.com/api/audit` |

Notes worth knowing before you demo it:

- `requirements.txt` pins the **CPU-only** PyTorch wheel. The default Linux wheel pulls the whole
  CUDA stack (several GB) and will run the service out of memory.
- The vector index (`data/chroma_db`) is committed, so a deployment loads it instead of
  re-embedding all 1268 corpus chunks. The retriever checks a fingerprint of the corpus and
  rebuilds the index automatically if the corpus ever changes.
- The pipeline warm-up runs in the background right after the port opens, so the health check
  responds immediately while the models load.
- The SQLite audit trail lives on the instance's ephemeral disk, so it resets on every deploy.

## 🧪 Example Workflow

A typical Reguard AI analysis looks like:

1. User submits lending policy
             ↓
2. Policy is parsed
             ↓
3. Important policy statements are identified
             ↓
4. Compliance queries are generated
             ↓
5. BM25 + Dense retrieval searches regulations
             ↓
6. Regulatory evidence is collected
             ↓
7. Specialized agents attack the policy
             ↓
8. Findings are validated
             ↓
9. Risks are categorized
             ↓
10. Remediation is generated
             ↓
11. Results are presented to the user