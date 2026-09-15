# Reguard AI — Generated Data Package

## Scope note on source PDFs
Four files were uploaded. Two (`RBI_digital_Guidline2.pdf` = RBI (Digital Lending)
Directions, 2025; `RBI_Penal_Charges_2023.pdf` = Fair Lending Practice - Penal
Charges circular) contain genuine, on-topic RBI regulatory text and are the
**only** sources used for `regulatory_corpus.json`. The third file
(`RBI_DLG_Digital_Lending_2023.pdf`, as uploaded) rendered as an RBI RTI
disclosure log (forex/UPI/HR/currency FAQs, not DLG rules) — it contains no
digital-lending regulatory obligations, so nothing was drawn from it; DLG
(Default Loss Guarantee) rules are already fully present natively in Chapter
VI, Paras 18–28 of the Digital Lending Directions PDF, so DLG coverage is not
missing. Nothing was invented to fill this gap.

## Files generated
- `corpus/regulatory_corpus.json` — 57 passages, sourced only from the two
  genuine PDFs above. No AML/KYC/PMLA, GDPR/DPDP, or HIPAA content.
- `policies/*.md` — 6 fictional company digital-lending policies
  (QuickLend, RapidCredit, PixelPay, TrustLend, SwiftCash, CredEasy),
  each containing 2 clause-pairs (4 clauses) across 12 topics total.
- `benchmarks/policy_loophole_eval_benchmark.json` — 24 cases (12 loophole /
  12 compliant), train=16 / dev=5 / test=3, each mapped to real
  `passage_id`s in the corpus.

## Validation performed (all passed)
1. Every benchmark `source_doc` has a corresponding policy file.
2. Every `clause_text` appears verbatim inside its referenced policy file.
3. Every `mapped_passage_ids` entry resolves to a real corpus `passage_id`.
4. Every loophole case has a non-empty `violation_type` + `evidence_summary`
   grounded in cited passage(s).
5. Every compliant case has a non-null `evidence_summary` and
   `violation_type: null`.
6. All 24 cases validated; label balance 12/12; splits 16/5/3 exact.
7. No AML/KYC/GDPR/DPDP/HIPAA regulatory content (checked for regulation-level
   references, not incidental words).
8. Both JSON files parse and re-serialize cleanly.
9. No RBI evidence was fabricated — every citation traces to an existing,
   verified passage already extracted from the source PDFs.
