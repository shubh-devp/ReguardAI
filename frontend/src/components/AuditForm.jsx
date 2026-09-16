import { useState } from 'react'

const EXAMPLE_CLAUSE =
  'The lender shall levy a penal charge of 2% per month on delayed repayments, compounded monthly until the outstanding amount is cleared in full.'

// Past this length the input reads as a whole document rather than a clause.
// The text is still submitted as typed; this only warns that an audit of a full
// document is harder to read than an audit of one clause.
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
    // Cleared straight away so picking the same file twice still fires a change.
    event.target.value = ''
    if (!file) return

    setReading(true)
    setImportNote('')
    setImportError('')

    try {
      // Loaded on demand so the PDF parser is not part of the initial page.
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
      className="no-print mt-8 rounded-lg border border-slate-200 bg-white p-6"
      onSubmit={(event) => {
        event.preventDefault()
        onRun()
      }}
    >
      <div>
        <label htmlFor="policy-name" className="block text-sm font-medium text-slate-700">
          Policy name
        </label>
        <input
          id="policy-name"
          type="text"
          value={policyName}
          disabled={loading}
          onChange={(event) => onPolicyNameChange(event.target.value)}
          placeholder="Digital_Lending_Policy.txt"
          className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none disabled:bg-slate-50"
        />
      </div>

      <div className="mt-5">
        <label htmlFor="clause-text" className="block text-sm font-medium text-slate-700">
          Policy / clause text
        </label>
        <textarea
          id="clause-text"
          rows={8}
          value={clauseText}
          disabled={loading}
          onChange={(event) => onClauseTextChange(event.target.value)}
          placeholder="Paste a lending policy clause here, or import a file below…"
          className="mt-1.5 w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm leading-relaxed focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none disabled:bg-slate-50"
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
              className="text-blue-600 hover:underline disabled:opacity-50"
            >
              Use example clause
            </button>

            <label
              htmlFor="policy-file"
              className={`text-blue-600 hover:underline ${
                loading || reading ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
              }`}
            >
              {reading ? 'Reading file…' : 'Import PDF or text file'}
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

          <span className="text-slate-500">{wordCount} words</span>
        </div>

        {importNote ? <p className="mt-1.5 text-xs text-slate-500">{importNote}</p> : null}
        {importError ? <p className="mt-1.5 text-xs text-red-600">{importError}</p> : null}
        {importNote && wordCount > LONG_INPUT_WORDS ? (
          <p className="mt-1.5 text-xs text-slate-500">
            That is a whole document rather than a single clause. The audit still runs, but it is
            easier to check the result against one clause at a time.
          </p>
        ) : null}
      </div>

      <button
        type="submit"
        disabled={loading || reading || !clauseText.trim()}
        className="mt-5 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {loading ? 'Running…' : 'Run Audit'}
      </button>
    </form>
  )
}
