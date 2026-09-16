import { useEffect, useState } from 'react'
import { fetchMetrics } from '../api/metrics'
import { formatPercent } from '../lib/format'

// Every figure below comes from GET /api/metrics, which serves the files the
// evaluation scripts wrote. Nothing here is hard-coded, so the panel cannot
// drift away from what was actually measured.

function Table({ head, rows }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200">
            {head.map((cell) => (
              <th key={cell} className="py-2 pr-4 text-xs font-medium tracking-wide text-slate-500 uppercase">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row[0]} className="border-b border-slate-100 last:border-0">
              {row.map((cell, index) => (
                <td key={index} className={`py-2 pr-4 ${index === 0 ? 'font-mono' : 'text-slate-700'}`}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Retrieval quality: how often the passage a finding needs is actually retrieved. */
function RetrievalTable({ retrieval }) {
  if (!retrieval?.strategies) return null

  const head = ['Strategy', 'Recall@4', 'Recall@8', 'MRR', 'nDCG@8']
  const rows = Object.entries(retrieval.strategies).map(([name, entry]) => {
    const macro = entry?.macro || {}
    return [
      name,
      formatPercent(macro['recall@4']),
      formatPercent(macro['recall@8']),
      formatPercent(macro.mrr),
      formatPercent(macro['ndcg@8']),
    ]
  })

  const best = retrieval.verdict?.['best_ndcg@8']

  return (
    <>
      <Table head={head} rows={rows} />
      <p className="text-xs text-slate-500">
        Measured over {retrieval.dataset?.total_clauses} clauses with gold evidence; the pipeline
        retrieves {retrieval.production_k} passages per query. Highest nDCG@8: {best || '—'}.
        {retrieval.verdict?.reranking_improves_hybrid === false
          ? ' Lexical reranking was measured and did not help, so it is not in the pipeline.'
          : ''}
      </p>
    </>
  )
}

/** The risk model: cross-validated scores, plus the shuffled-label control. */
function MlPanel({ ml }) {
  if (!ml?.candidates) return null

  const rows = Object.entries(ml.candidates).map(([name, entry]) => {
    const summary = entry.summary || {}
    return [
      name,
      formatPercent(summary.f1?.median),
      formatPercent(summary.roc_auc?.median),
      `${formatPercent(summary.f1?.min)}–${formatPercent(summary.f1?.max)}`,
    ]
  })

  const control = ml.shuffled_label_control?.[ml.shipped_model?.name]
  const gate = ml.gate_behaviour

  return (
    <>
      <Table
        head={['Model (5-fold CV, median)', 'F1', 'ROC-AUC', 'F1 range across folds']}
        rows={rows}
      />
      <p className="text-xs text-slate-500">
        Shipped: <span className="font-mono">{ml.shipped_model?.name}</span>
        {control ? (
          <>
            {' '}
            · shuffled-label control F1 {formatPercent(control.f1?.median)}, which is the same as
            the real labels on a {ml.dataset?.total_clauses}-clause benchmark. The triage model is
            a gate, not the source of the finding.
          </>
        ) : null}
      </p>
      {gate ? (
        <p className="text-xs text-slate-500">
          Gate at {gate.threshold}: {gate.flagged_for_red_teaming}/{gate.of_total} clauses flagged
          (precision {formatPercent(gate.precision)}, recall {formatPercent(gate.recall)}), so the
          adversarial stages see everything.
        </p>
      ) : null}
      {ml.caveats?.length ? (
        <ul className="list-disc space-y-1 pl-5 text-xs text-slate-500">
          {ml.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      ) : null}
    </>
  )
}

/**
 * Shows what the model and the retriever actually score. It is collapsed by
 * default so the audit result stays the first thing on the page.
 */
export default function ModelMetrics() {
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchMetrics()
      .then((data) => {
        if (!cancelled) setMetrics(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="mt-8 rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between px-6 py-4 text-left"
      >
        <div>
          <h3 className="text-base font-semibold text-slate-900">Measured performance</h3>
          <p className="text-xs text-slate-500">
            Retrieval scores and model cross-validation, read from the evaluation result files.
          </p>
        </div>
        <span className="text-sm text-slate-500">{open ? 'Hide' : 'Show'}</span>
      </button>

      {open ? (
        <div className="space-y-6 border-t border-slate-200 px-6 py-5 text-sm text-slate-700">
          {error ? <p className="text-red-600">{error}</p> : null}
          {!metrics && !error ? <p className="text-slate-500">Loading metrics…</p> : null}

          {metrics ? (
            <>
              <div>
                <h4 className="text-xs font-medium tracking-wide text-slate-500 uppercase">
                  Retrieval (BM25 + dense hybrid RAG)
                </h4>
                <div className="mt-3">
                  <RetrievalTable retrieval={metrics.retrieval} />
                </div>
              </div>

              <div>
                <h4 className="text-xs font-medium tracking-wide text-slate-500 uppercase">
                  Risk triage model
                </h4>
                <div className="mt-3 space-y-3">
                  <MlPanel ml={metrics.ml} />
                </div>
              </div>

              {metrics.retrieval?.caveats?.length ? (
                <div>
                  <h4 className="text-xs font-medium tracking-wide text-slate-500 uppercase">
                    Retrieval caveats
                  </h4>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-500">
                    {metrics.retrieval.caveats.map((caveat) => (
                      <li key={caveat}>{caveat}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
