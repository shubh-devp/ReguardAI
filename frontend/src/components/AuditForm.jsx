
import { useState } from 'react'

const EXAMPLE_CLAUSE =
  'The lender shall levy a penal charge of 2% per month on delayed repayments, compounded monthly until the outstanding amount is cleared in full.'

const LONG_INPUT_WORDS = 800

/**
 * The audit input form. Controlled by App so the values survive re-renders.
 */
export default function AuditForm({
  policyName,
  clauseText,
  onPolicyNameChange,
  onClauseTextChange,
  onRun,
  loading,
}) {
  const [reading, setReading] = useState(false)
  const [importNote, setImportNote] = useState('')
  const [importError, setImportError] = useState('')

  const wordCount = clauseText.trim() ? clauseText.trim().split(/\s+/).length : 0

  async function handleFile(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    setReading(true)
    setImportNote('')
    setImportError('')

    try {
      const { readDocument } = await import('../lib/pdf')
      const { text, note } = await readDocument(file)
      if (!text) {
        setImportError(
          file.name.toLowerCase().endsWith('.pdf')
            ? 'No text found in that PDF. If it is a scan, the pages are images and the text has to be typed or pasted.'
            : 'That file looked empty.',
        )
        return
      }
      onClauseTextChange(text)
      onPolicyNameChange(file.name)
      setImportNote(`Imported ${file.name} — ${note}. Check the text before running the audit.`)
    } catch (error) {
      setImportError(`Could not read that file: ${error.message}`)
    } finally {
      setReading(false)
    }
  }

  return (
    <form
      className="no-print mt-6 rounded-md border border-slate-200 bg-white p-5 shadow-sm"
      onSubmit={(event) => {
        event.preventDefault()
        onRun()
      }}
    >
      <div>
        <label htmlFor="policy-name" className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
          Policy Name
        </label>
        <input
          id="policy-name"
          type="text"
          value={policyName}
          disabled={loading}
          onChange={(event) => onPolicyNameChange(event.target.value)}
          placeholder="Digital_Lending_Policy.txt"
          className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-900 transition-colors focus:border-slate-900 focus:outline-none disabled:bg-slate-50 disabled:text-slate-400"
        />
      </div>

      <div className="mt-4">
        <label htmlFor="clause-text" className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
          Policy / Clause Text
        </label>
        <textarea
          id="clause-text"
          rows={7}
          value={clauseText}
          disabled={loading}
          onChange={(event) => onClauseTextChange(event.target.value)}
          placeholder="Paste a lending policy clause here, or import a file below..."
          className="mt-1 w-full resize-y rounded border border-slate-300 px-3 py-2 text-sm leading-relaxed text-slate-900 transition-colors focus:border-slate-900 focus:outline-none disabled:bg-slate-50 disabled:text-slate-400 font-mono text-xs"
        />

        <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-xs">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={loading || reading}
              onClick={() => {
                onPolicyNameChange('Digital_Lending_Policy.txt')
                onClauseTextChange(EXAMPLE_CLAUSE)
                setImportNote('')
                setImportError('')
              }}
              className="font-medium text-slate-700 underline decoration-slate-300 underline-offset-2 hover:text-slate-900 hover:decoration-slate-900 disabled:opacity-50"
            >
              Use example clause
            </button>

            <label
              htmlFor="policy-file"
              className={`font-medium text-slate-700 underline decoration-slate-300 underline-offset-2 hover:text-slate-900 hover:decoration-slate-900 ${
                loading || reading ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
              }`}
            >
              {reading ? 'Reading file...' : 'Import PDF or text file'}
            </label>
            <input
              id="policy-file"
              type="file"
              accept=".pdf,.txt,text/plain,application/pdf"
              disabled={loading || reading}
              onChange={handleFile}
              className="sr-only"
            />
          </div>

          <span className="text-slate-500 tabular-nums">{wordCount} words</span>
        </div>

        {importNote ? <p className="mt-2 text-xs text-slate-600">{importNote}</p> : null}
        {importError ? <p className="mt-2 text-xs font-medium text-rose-600">{importError}</p> : null}
        {importNote && wordCount > LONG_INPUT_WORDS ? (
          <p className="mt-2 text-xs text-amber-700 bg-amber-50 p-2 rounded border border-amber-200">
            Note: That reads as a full document rather than a single clause. The audit will still run, but clause-by-clause reviews provide sharper findings.
          </p>
        ) : null}
      </div>

      <div className="mt-5 flex items-center justify-end">
        <button
          type="submit"
          disabled={loading || reading || !clauseText.trim()}
          className="rounded bg-slate-900 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
        >
          {loading ? 'Running Audit...' : 'Run Compliance Audit'}
        </button>
      </div>
    </form>
  )
}