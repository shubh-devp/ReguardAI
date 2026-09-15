const EXAMPLE_CLAUSE =
  'The lender shall levy a penal charge of 2% per month on delayed repayments, compounded monthly until the outstanding amount is cleared in full.'

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
  const wordCount = clauseText.trim() ? clauseText.trim().split(/\s+/).length : 0

  return (
    <form
      className="mt-8 rounded-lg border border-slate-200 bg-white p-6"
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
          placeholder="Paste a lending policy clause here…"
          className="mt-1.5 w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm leading-relaxed focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none disabled:bg-slate-50"
        />
        <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              onPolicyNameChange('Digital_Lending_Policy.txt')
              onClauseTextChange(EXAMPLE_CLAUSE)
            }}
            className="text-blue-600 hover:underline disabled:opacity-50"
          >
            Use example clause
          </button>
          <span>{wordCount} words</span>
        </div>
      </div>

      <button
        type="submit"
        disabled={loading || !clauseText.trim()}
        className="mt-5 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {loading ? 'Running…' : 'Run Audit'}
      </button>
    </form>
  )
}
