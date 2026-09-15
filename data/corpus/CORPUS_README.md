# Reguard AI — RBI Digital Lending / Fair Lending Regulatory Corpus

This corpus supports the **Reguard AI — Autonomous Regulatory Compliance
Red-Teaming Engine** portfolio project. It has been rebuilt to match the
project's locked scope: **Fintech & Digital Lending (RBI/Financial
Compliance)**. It was built exclusively from two source PDFs supplied by the
project owner, with no web search and no regulatory content added from model
knowledge.

## Source documents

| File | Authority | Instrument | Pages used |
|---|---|---|---|
| `RBI_digital_Guidline2.pdf` | Reserve Bank of India | Reserve Bank of India (Digital Lending) Directions, 2025 (RBI/2025-26/36, DOR.STR.REC.19/21.07.001/2025-26, dated May 8, 2025) | Chapters I–VII (pages 3–20); Annexes I–III not separately chunked (tabular/list content) |
| `RBI_Penal_Charges_2023.pdf` | Reserve Bank of India | Fair Lending Practice – Penal Charges in Loan Accounts (RBI/2023-24/53, DoR.MCS.REC.28/01.01.001/2023-24, dated August 18, 2023) | Circular body (pages 1–3) and one representative Annex passage on Board-approved interest rate/penal charge policy (page 5) |

Both PDFs are digitally authored (the Digital Lending Directions is a clean
text PDF; the Penal Charges circular carries a diagonal "Withdrawn" watermark
overlay from RBI's website, which was ignored as a rendering artifact and not
transcribed into any passage). Text was extracted directly from the supplied
PDF content. No wording, numbers, or legal content were altered, added, or
guessed.

**Note on the Penal Charges circular's "Withdrawn" watermark:** the source
PDF as supplied is stamped "Withdrawn" across every page (this is how RBI
marks circulars on its site once a provision has been superseded/consolidated
elsewhere — in this case, the substance of RBI/2023-24/53 was carried forward
into Para 8(ii) and other provisions of the 2025 Digital Lending Directions,
which cross-references this circular directly). This corpus still treats the
circular's passages as `status: active` because the Digital Lending
Directions (the newer, controlling instrument) explicitly incorporates it by
reference (`RBI-DL-0012`); however, a human reviewer relying on this corpus
for a live compliance decision should independently confirm on the RBI
website whether the original circular has been separately superseded, since
"Withdrawn" is exactly the kind of status flag this corpus's own schema is
designed to carry once confirmed.

## Corpus construction methodology

1. **Inventory.** Both PDFs were read in full; the Digital Lending Directions
   runs 24 printed pages (index + 30 numbered paragraphs across 7 chapters +
   3 annexes), and the Penal Charges circular runs to its main 3-page body
   plus a lengthy Annex tabulating amendments to five separate Master
   Directions/Circulars.
2. **Passage selection.** Passages were drawn at legally meaningful
   boundaries — each numbered paragraph or logically grouped sub-clauses
   within it — chosen to be self-contained enough to state a single
   obligation or a closely related group of obligations, consistent with the
   prior corpus's own methodology. Where a paragraph covers several
   independent obligations (e.g. Para 9 on loan disbursal/servicing, or
   Chapter VI's DLG provisions), it was split into multiple passages along
   its own lettered/numbered sub-structure.
3. **Scope decision (stated explicitly).** This rebuild intentionally
   **replaces** the prior corpus's AML/KYC/PMLA content — that material is
   out of the current project scope. Coverage here focuses on the
   obligations most relevant to loophole/fair-lending detection in digital
   lending: APR/Key Fact Statement disclosure, cooling-off period, direct
   disbursal (no LSP pass-through account), penal charges (flat, disclosed,
   non-compounded, non-discriminatory), RE-LSP due diligence and governance,
   DLA/LSP disclosure obligations, grievance redressal, credit-limit
   consent, data collection/storage/consent, recovery-agent conduct, and
   First Loss/Default Loss Guarantee (FLDG/DLG) structure and caps. The
   Digital Lending Directions' Annex I (a blank CIMS reporting data-field
   table) and Annex II (worked numerical illustrations of DLG cover
   mechanics) were reviewed but not chunked as separate passages, since they
   are tabular/illustrative rather than freestanding obligations; their
   substance is already captured in the paragraph 17 and paragraph 23
   passages they illustrate. The bulk of the Penal Charges circular's Annex
   (five near-identical amendment tables applying the same penal-charges
   language across different Master Directions/Circulars) was represented by
   **one** illustrative passage (`RBI-PENAL-0010`) rather than five duplicate
   passages, since the operative language is identical to Para 3 of the same
   circular (already captured in `RBI-PENAL-0003` through `RBI-PENAL-0007`)
   and the marginal retrieval value of the repeated table rows is low; the
   one included passage documents the Board-approved interest-rate-model
   angle (gradation of risk, annualised rate) that Para 3 does not otherwise
   cover.
4. **Metadata extraction.** Same schema and discipline as the prior corpus:
   `page` reflects the printed page number visible in the source PDF;
   `effective_date` is populated only where the source text itself states a
   commencement/effective date tied to that specific provision (e.g. Para 6
   and Para 17 of the Digital Lending Directions have different commencement
   dates than the rest of the instrument, and are noted accordingly); `null`
   otherwise.
5. **Text fidelity.** Every `text` field is a verbatim (or near-verbatim,
   where a passage merges lettered sub-points — (a), (b), (c) — into a single
   flowing sentence for chunk coherence) transcription of the source
   passage. No paraphrase, summary, or interpretive gloss is present.

## Passage schema

Unchanged from the prior corpus (see field-by-field description in the
project's original documentation). `passage_id` prefixes: `RBI-DL-####` for
the 2025 Digital Lending Directions, `RBI-PENAL-####` for the 2023 Penal
Charges circular. IDs are zero-padded, sequential per source, and stable.

## Data-quality report

**Corpus (`regulatory_corpus.json`)** — 57 passages total (rebuilt from 80
AML/KYC-domain passages in the prior version, which have been fully removed).

| Source | Passages | Distinct sections cited |
|---|---|---|
| `RBI_digital_Guidline2.pdf` | 47 | 47 |
| `RBI_Penal_Charges_2023.pdf` | 10 | 10 |
| **Total** | **57** | **57** |

- Passages with page metadata: 57 / 57 (100%)
- Passages with section metadata: 57 / 57 (100%)
- Passages with `subsection` = null: 3 / 57 (whole-paragraph passages with no
  further sub-label needed)
- Passages with `effective_date` = null: 53 / 57 (base text with no
  provision-specific commencement date distinct from the instrument's
  overall effective date)
- Duplicate `passage_id` values: 0
- Duplicate `text` values: 0
- All `status` values: `active` (see the Penal Charges "Withdrawn" watermark
  note above for the one caveat a human reviewer should independently
  confirm)

## Benchmark re-mapping

`policy_loophole_eval_benchmark.json`'s 24 clauses were previously mapped
against 13 placeholder `passage_id` values (`RBI-DL-KFS-APR-01`,
`RBI-DL-COOLOFF-01`, etc.) that did not correspond to any real corpus
passage, since they were authored before this corpus existed. All 13
placeholders have now been resolved to real `passage_id` values in the
rebuilt corpus above (e.g. `RBI-DL-KFS-APR-01` → `RBI-DL-0004` +
`RBI-DL-0012`), and every clause's `mapped_passage_ids` list has been
verified to resolve to passages that exist in `regulatory_corpus.json`. This
mapping is a first-pass, LLM-assisted alignment based on matching each
clause's stated `topic`/`violation_type` to the closest corpus passage(s); as
with the prior corpus's own AML/KYC mapping, it should be treated as
`review_required` rather than independently `verified` by a human SME before
being used as ground truth for retrieval evaluation (Recall@K / MRR).

## How this corpus should be used in RAG

Unchanged from the prior corpus: retrieval index only (embed/BM25-index the
`text` field, optionally concatenated with `regulation` + `section` +
`topic` + `keywords`); evidence, not verdicts (a Regulatory Auditor/Evidence
Verifier agent should quote or closely paraphrase retrieved `text` and cite
`passage_id` + `source_document` + `page`); grounding discipline (an
ungrounded claim should be flagged as such, not asserted); and the raw PDFs
remain the ultimate source of truth for any output informing a compliance
decision.
