// import { useState } from 'react'
// import { runAudit } from './api/audit'
// import AuditForm from './components/AuditForm'
// import AuditResults from './components/AuditResults'
// import ModelMetrics from './components/ModelMetrics'

// const DEFAULT_CLAUSE =
//   'The lender shall levy a penal charge of 2% per month on delayed repayments, compounded monthly until the outstanding amount is cleared in full.'

// export default function App() {
//   const [policyName, setPolicyName] = useState('Digital_Lending_Policy.txt')
//   const [clauseText, setClauseText] = useState(DEFAULT_CLAUSE)

//   const [loading, setLoading] = useState(false)
//   const [error, setError] = useState('')
//   const [result, setResult] = useState(null)
//   // Kept separately because the API echoes back the patched clause, not the original.
//   const [auditedClause, setAuditedClause] = useState('')

//   async function handleRunAudit() {
//     const clause = clauseText.trim()
//     if (!clause) return

//     setLoading(true)
//     setError('')
//     setResult(null)

//     try {
//       const data = await runAudit({ policyName: policyName.trim() || 'policy.txt', clauseText: clause })
//       setAuditedClause(clause)
//       setResult(data)
//     } catch (err) {
//       setError(err.message)
//     } finally {
//       setLoading(false)
//     }
//   }

//   return (
//     <div className="min-h-screen">
//       <header className="no-print border-b border-slate-200 bg-white">
//         <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3 px-6 py-5">
//           <div>
//             <h1 className="text-lg font-semibold text-slate-900">Reguard AI</h1>
//             <p className="text-sm text-slate-500">Digital Lending Regulatory Compliance</p>
//           </div>
//           <span className="rounded border border-slate-200 px-2.5 py-1 text-xs text-slate-600">
//             RBI · Fintech
//           </span>
//         </div>
//       </header>

//       <main className="mx-auto max-w-3xl px-6 py-10">
//         <h2 className="no-print text-2xl font-semibold tracking-tight text-slate-900">
//           Regulatory Compliance Audit
//         </h2>
//         <p className="no-print mt-2 text-sm leading-relaxed text-slate-600">
//           Paste a lending policy clause below. Reguard AI scores its risk, red-teams it the way a
//           borrower would, checks it against RBI regulation and drafts a compliant rewrite.
//         </p>

//         <AuditForm
//           policyName={policyName}
//           clauseText={clauseText}
//           onPolicyNameChange={setPolicyName}
//           onClauseTextChange={setClauseText}
//           onRun={handleRunAudit}
//           loading={loading}
//         />

//         {loading ? (
//           <div className="mt-8 flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-6">
//             <span className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
//             <div>
//               <p className="text-sm font-medium text-slate-900">Running compliance audit…</p>
//               <p className="text-xs text-slate-500">
//                 The backend runs all agents in one request, so this can take a few minutes.
//               </p>
//             </div>
//           </div>
//         ) : null}

//         {!loading && error ? (
//           <div className="mt-8 rounded-lg border border-red-200 bg-red-50 p-6">
//             <p className="text-sm font-medium text-red-700">Audit failed</p>
//             <p className="mt-1 text-sm text-red-600">{error}</p>
//           </div>
//         ) : null}

//         {!loading && !error && result ? (
//           <AuditResults result={result} originalClause={auditedClause} />
//         ) : null}

//         {!loading && !error && !result ? (
//           <p className="mt-8 text-sm text-slate-500">
//             Results will appear here after you run an audit.
//           </p>
//         ) : null}

//         <ModelMetrics />
//       </main>

//       <footer className="no-print border-t border-slate-200 py-6">
//         <p className="mx-auto max-w-3xl px-6 text-xs text-slate-500">
//           Reguard AI — multi-agent compliance checker for digital lending policies.
//         </p>
//       </footer>
//     </div>
//   )
// }





import { useState } from 'react'
import { runAudit } from './api/audit'
import AuditForm from './components/AuditForm'
import AuditResults from './components/AuditResults'
import ModelMetrics from './components/ModelMetrics'

const DEFAULT_CLAUSE =
  'The lender shall levy a penal charge of 2% per month on delayed repayments, compounded monthly until the outstanding amount is cleared in full.'

export default function App() {
  const [policyName, setPolicyName] = useState('Digital_Lending_Policy.txt')
  const [clauseText, setClauseText] = useState(DEFAULT_CLAUSE)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [auditedClause, setAuditedClause] = useState('')

  async function handleRunAudit() {
    const clause = clauseText.trim()
    if (!clause) return

    setLoading(true)
    setError('')
    setResult(null)

    try {
      const data = await runAudit({ policyName: policyName.trim() || 'policy.txt', clauseText: clause })
      setAuditedClause(clause)
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50/30 text-slate-900 font-sans antialiased">
      <header className="no-print border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3 px-6 py-4">
          <div>
            <h1 className="text-sm font-bold uppercase tracking-wider text-slate-900">Reguard AI</h1>
            <p className="text-xs text-slate-500">Digital Lending Regulatory Compliance Engine</p>
          </div>
          <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-mono text-slate-600">
            RBI · Fintech
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-8">
        <h2 className="no-print text-xl font-bold tracking-tight text-slate-900">
          Regulatory Compliance Audit
        </h2>
        <p className="no-print mt-1.5 text-xs leading-relaxed text-slate-600">
          Paste a lending policy clause below. Reguard AI scores risk, red-teams scenarios the way a borrower would, verifies RBI regulations, and drafts compliant rewrites.
        </p>

        <AuditForm
          policyName={policyName}
          clauseText={clauseText}
          onPolicyNameChange={setPolicyName}
          onClauseTextChange={setClauseText}
          onRun={handleRunAudit}
          loading={loading}
        />

        {loading ? (
          <div className="mt-6 flex items-center gap-3 rounded-md border border-slate-200 bg-white p-5 shadow-sm">
            <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-slate-200 border-t-slate-900" />
            <div>
              <p className="text-xs font-semibold text-slate-900">Running compliance audit pipeline...</p>
              <p className="text-xs text-slate-500 mt-0.5">
                Executing multi-agent evaluation across retrieval, triage, red-teaming, and re-test steps. This may take a moment.
              </p>
            </div>
          </div>
        ) : null}

        {!loading && error ? (
          <div className="mt-6 rounded-md border border-rose-200 bg-rose-50 p-4">
            <p className="text-xs font-bold uppercase tracking-wider text-rose-700">Audit Failed</p>
            <p className="mt-1 text-xs font-medium text-rose-600">{error}</p>
          </div>
        ) : null}

        {!loading && !error && result ? (
          <AuditResults result={result} originalClause={auditedClause} />
        ) : null}

        {!loading && !error && !result ? (
          <p className="mt-6 text-xs text-slate-400 font-medium">
            Audit reports and verifiable evidence will appear here after execution.
          </p>
        ) : null}

        <ModelMetrics />
      </main>

      <footer className="no-print border-t border-slate-200 bg-white py-5 mt-12">
        <p className="mx-auto max-w-3xl px-6 text-xs text-slate-500">
          Reguard AI — Multi-agent compliance validation engine for digital lending policy frameworks.
        </p>
      </footer>
    </div>
  )
}