import { useEffect, useState } from 'react'
import { fetchMetrics } from '../api/metrics'
import { formatPercent } from '../lib/format'

function Table({ head, rows }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-slate-200">
            {head.map((cell) => (
              <th key={cell} className="py-2 pr-4 font-semibold tracking-wider text-slate-500 uppercase">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={row[0]}>
              {row.map((cell, index) => (
                <td key={index} className={`py-2.5 pr-4 ${index === 0 ? 'font-mono font-medium text-slate-900' : 'text-slate-700'}`}>
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
    <div className="space-y-3">
      <Table head={head} rows={rows} />
      <p className="text-xs text-slate-500">
        Measured over {retrieval.dataset?.total_clauses} clauses with gold evidence; the pipeline retrieves {retrieval.production_k} passages per query. Highest nDCG@8: <span className="font-semibold text-slate-700">{best || '—'}</span>.
        {retrieval.verdict?.reranking_improves_hybrid === false
          ? ' Lexical reranking was tested and did not improve performance, so it was excluded from production.'
          : ''}
      </p>
    </div>
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
    <div className="space-y-3">
      <Table
        head={['Model (5-fold CV median)', 'F1', 'ROC-AUC', 'F1 Range Across Folds']}
        rows={rows}
      />
      <p className="text-xs text-slate-500">
        Shipped: <span className="font-mono font-medium text-slate-700">{ml.shipped_model?.name}</span>
        {control ? (
          <>
            {' '}
            · Shuffled-label control F1 {formatPercent(control.f1?.median)}, matching real labels on a {ml.dataset?.total_clauses}-clause benchmark. The triage model acts as a gate, not the final source of findings.
          </>
        ) : null}
      </p>
      {gate ? (
        <p className="text-xs text-slate-500">
          Gate at threshold {gate.threshold}: {gate.flagged_for_red_teaming}/{gate.of_total} clauses flagged (precision {formatPercent(gate.precision)}, recall {formatPercent(gate.recall)}), ensuring adversarial stages evaluate all candidates.
        </p>
      ) : null}
      {ml.caveats?.length ? (
        <ul className="list-disc space-y-1 pl-4 text-xs text-slate-500">
          {ml.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

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
    <section className="no-print mt-6 rounded-md border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between px-5 py-4 text-left transition-colors hover:bg-slate-50/50"
      >
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-800">Measured Performance Metrics</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Retrieval validation scores and model cross-validation results from evaluation suites.
          </p>
        </div>
        <span className="text-xs font-semibold text-slate-600 underline decoration-slate-300 underline-offset-2">
          {open ? 'Hide Metrics' : 'Show Metrics'}
        </span>
      </button>

      {open ? (
        <div className="space-y-6 border-t border-slate-200 px-5 py-4 text-sm text-slate-700">
          {error ? <p className="text-xs font-medium text-rose-600">{error}</p> : null}
          {!metrics && !error ? <p className="text-xs text-slate-500">Loading evaluation metrics...</p> : null}

          {metrics ? (
            <>
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Retrieval (BM25 + Dense Hybrid RAG)
                </h4>
                <div className="mt-2">
                  <RetrievalTable retrieval={metrics.retrieval} />
                </div>
              </div>

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Risk Triage Model
                </h4>
                <div className="mt-2">
                  <MlPanel ml={metrics.ml} />
                </div>
              </div>

              {metrics.retrieval?.caveats?.length ? (
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Retrieval Caveats
                  </h4>
                  <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-slate-500">
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
