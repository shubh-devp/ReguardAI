import {
  deltaIsImprovement,
  describeConsensus,
  describeStatus,
  describeVerdict,
  formatDelta,
  formatPercent,
  levelColor,
} from '../lib/format'

function Card({ title, subtitle, children }) {
  return (
    <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-800">{title}</h3>
      {subtitle ? <p className="mt-1 text-xs text-slate-500">{subtitle}</p> : null}
      <div className="mt-4 space-y-4 text-sm text-slate-700">{children}</div>
    </section>
  )
}

function Label({ children }) {
  return (
    <span className="text-xs font-semibold tracking-wider text-slate-500 uppercase">{children}</span>
  )
}

function Metric({ label, value, valueClass = 'text-slate-900' }) {
  return (
    <div>
      <Label>{label}</Label>
      <div className={`mt-0.5 text-lg font-semibold tracking-tight ${valueClass}`}>{value}</div>
    </div>
  )
}

function Clause({ label, text, highlight = false }) {
  return (
    <div
      className={`rounded border p-3.5 ${
        highlight ? 'border-slate-300 bg-slate-50/80 font-medium' : 'border-slate-200 bg-slate-50/40'
      }`}
    >
      <Label>{label}</Label>
      <p className="mt-1.5 leading-relaxed text-slate-800 text-xs font-mono">{text || '—'}</p>
    </div>
  )
}

/**
 * The red team's per-surface verdicts. One row per attacker, so a surface that
 * disagreed with the others is visible rather than averaged away.
 */
function RedTeamCard({ redTeam, attacks, attack }) {
  if (!redTeam) return null

  return (
    <Card
      title="Red Team Analysis"
      subtitle={`${redTeam.attacks_generated} specialized agents executed in parallel`}
    >
      <div className="grid gap-4 sm:grid-cols-3 border-b border-slate-100 pb-4">
        <Metric label="Surfaces Flagged" value={`${redTeam.surfaces_flagged} / ${redTeam.attacks_generated}`} />
        <Metric label="Agreement" value={formatPercent(redTeam.agreement)} />
        <Metric
          label="Highest Severity"
          value={redTeam.highest_severity || '—'}
          valueClass={levelColor(redTeam.highest_severity)}
        />
      </div>

      <p className="text-xs text-slate-600 font-medium">{describeConsensus(redTeam.consensus)}</p>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200">
              {['Surface', 'Verdict', 'Severity', 'Status'].map((cell) => (
                <th key={cell} className="py-2 pr-4 font-semibold tracking-wider text-slate-500 uppercase">
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(attacks || []).map((item) => (
              <tr key={item.surface}>
                <td className="py-2.5 pr-4 font-medium text-slate-900">{item.title || item.surface}</td>
                <td className={`py-2.5 pr-4 font-semibold ${item.vulnerability_detected ? 'text-rose-600' : 'text-emerald-700'}`}>
                  {item.vulnerability_detected ? 'Vulnerable' : 'Clear'}
                </td>
                <td className={`py-2.5 pr-4 font-semibold ${levelColor(item.severity)}`}>{item.severity}</td>
                <td className="py-2.5 pr-4 text-slate-500">
                  {item.failed
                    ? 'Agent failed — treated as not cleared'
                    : item.surface === attack?.surface
                      ? 'Carried into audit'
                      : 'Reported only'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {redTeam.failed_surfaces?.length ? (
        <p className="text-xs text-amber-700 bg-amber-50 p-2 rounded border border-amber-200">
          {redTeam.failed_surfaces.join(', ')} did not return a verdict, so those surfaces were not cleared.
        </p>
      ) : null}
    </Card>
  )
}

/** Where the decision came from: document, page, section and the runners-up. */
function EvidenceCard({ evidence, audit }) {
  if (!evidence || !evidence.citation) {
    return (
      <Card title="Regulatory Evidence">
        <p className="rounded border border-slate-200 bg-slate-50 p-3.5 leading-relaxed text-xs font-mono">
          {audit?.retrieved_passage || 'No statutory passage was returned for this audit.'}
        </p>
        <p className="text-xs text-slate-500">
          {evidence?.retrieval_failed
            ? 'Retrieval failed for this audit, so the passage above is a fixed fallback and is not evidence.'
            : 'No retrieved passage was attached to this finding.'}
        </p>
      </Card>
    )
  }

  const currency = evidence.currency || {}
  const otherWarnings = (currency.warnings || []).filter(
    (warning) => !warning.startsWith('effective date not recorded'),
  )

  return (
    <Card title="Regulatory Evidence" subtitle={evidence.citation}>
      <div className="grid gap-4 sm:grid-cols-3 border-b border-slate-100 pb-3">
        <Metric label="Passage ID" value={evidence.passage_id || 'no curated entry'} />
        <Metric label="Section" value={evidence.section || 'no curated entry'} />
        <Metric label="Status" value={currency.status || 'not recorded'} />
      </div>

      <div>
        <Label>Cited Passage</Label>
        <p className="mt-1.5 rounded border border-slate-200 bg-slate-50 p-3.5 leading-relaxed text-xs font-mono text-slate-800">
          {evidence.passage_text || audit?.retrieved_passage || '—'}
        </p>
      </div>

      <p className="text-xs text-slate-500">
        Effective date{' '}
        <span className="font-mono text-slate-700">{currency.effective_date || 'not recorded in corpus'}</span>
        {typeof currency.age_days === 'number' ? ` · ${currency.age_days} days old as of ${currency.as_of}` : ''}
      </p>

      {otherWarnings.length ? (
        <ul className="list-disc space-y-1 pl-4 text-xs text-amber-700 bg-amber-50 p-2 rounded border border-amber-200">
          {otherWarnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}

      {evidence.candidates?.length ? (
        <div className="pt-2">
          <Label>Also Retrieved</Label>
          <ul className="mt-2 space-y-2">
            {evidence.candidates.map((candidate, index) => (
              <li key={`${candidate.citation}-${index}`} className="rounded border border-slate-200 bg-slate-50/50 p-2.5">
                <p className="text-xs text-slate-500 font-mono">
                  <span>{candidate.citation || candidate.document}</span>
                  {candidate.passage_id ? ` · ${candidate.passage_id}` : ''}
                  {candidate.section ? ` · ${candidate.section}` : ''}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-slate-600">{candidate.snippet}…</p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  )
}

function outcomeLabel(outcome) {
  if (outcome === null || outcome === undefined) return 'Not measured'
  return outcome ? 'Defeated' : 'Blocked'
}

function outcomeClass(outcome) {
  if (outcome === null || outcome === undefined) return 'text-slate-500'
  return outcome ? 'text-rose-600 font-medium' : 'text-emerald-700 font-medium'
}

/** ASR before and after, measured over the same attack set both times. */
function ReTestCard({ retest }) {
  if (!retest) {
    return (
      <Card title="Attack Success Rate (Re-Test)">
        <p className="text-slate-600 text-xs">
          No re-test metrics were returned for this audit, so no ASR values are shown.
        </p>
      </Card>
    )
  }

  const verdict = describeVerdict(retest.verdict)

  return (
    <Card
      title="Attack Success Rate (Re-Test)"
      subtitle={`ASR share across the ${retest.total_attacks} attacks before and after patching`}
    >
      <div className="space-y-3 border-b border-slate-100 pb-4">
        <AsrBar
          label="Attacks that defeated the clause before the patch"
          value={retest.asr_before}
          tone="bg-slate-700"
        />
        <AsrBar
          label="Attacks that defeat it after the patch"
          value={retest.asr_after}
          tone="bg-blue-600"
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-3 border-b border-slate-100 pb-4">
        <Metric
          label="Change"
          value={formatDelta(retest.asr_before, retest.asr_after)}
          valueClass={
            deltaIsImprovement(retest.asr_before, retest.asr_after) ? 'text-emerald-700' : 'text-rose-600'
          }
        />
        <Metric label="Verdict" value={verdict.label} valueClass={verdict.color} />
        <Metric
          label="Exploits Blocked"
          value={
            retest.remediation_success_rate == null
              ? 'n/a'
              : formatPercent(retest.remediation_success_rate)
          }
        />
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Metric label="Attacks Run" value={retest.total_attacks ?? '—'} />
        <Metric label="Defeated Before" value={retest.original_successes ?? '—'} valueClass="text-rose-600" />
        <Metric
          label="Defeated After"
          value={retest.patched_successes ?? '—'}
          valueClass={retest.patched_successes === 0 ? 'text-emerald-700' : 'text-amber-600'}
        />
      </div>

      <p className="text-xs text-slate-500">
        {retest.verdict === 'no_vulnerability_detected'
          ? 'No attack succeeded even before the patch, so the re-test cannot demonstrate a fix.'
          : 'Only a clean sweep counts as fully mitigated; partial reductions are reported as partial.'}
      </p>

      {retest.measurement_complete === false ? (
        <p className="text-xs text-amber-700 bg-amber-50 p-2 rounded border border-amber-200">
          {retest.unmeasured_attacks} of {retest.total_attacks} attacks could not be measured. Rates cover the {retest.measured_attacks} measured attacks.
        </p>
      ) : null}

      {retest.per_attack?.length ? (
        <div className="overflow-x-auto pt-2">
          <Label>Per Attack Breakdown</Label>
          <table className="mt-2 w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200">
                {['Surface', 'Before', 'After', 'Outcome'].map((cell) => (
                  <th key={cell} className="py-2 pr-4 font-semibold tracking-wider text-slate-500 uppercase">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {retest.per_attack.map((row) => (
                <tr key={row.surface}>
                  <td className="py-2.5 pr-4 font-medium text-slate-900">{row.title || row.surface}</td>
                  <td className={`py-2.5 pr-4 ${outcomeClass(row.succeeded_before)}`}>
                    {outcomeLabel(row.succeeded_before)}
                  </td>
                  <td className={`py-2.5 pr-4 ${outcomeClass(row.succeeded_after)}`}>
                    {outcomeLabel(row.succeeded_after)}
                  </td>
                  <td className="py-2.5 pr-4 text-slate-500">
                    {!row.measured
                      ? 'Not measured'
                      : row.blocked_by_patch
                        ? 'Closed by patch'
                        : row.regression
                          ? 'Regression — new attack works'
                          : row.succeeded_after
                            ? 'Still open'
                            : 'Never worked'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  )
}

/**
 * The six stages the clause passes through, in order. A stage that did not run
 * is shown as skipped rather than hidden, so the report never reads as though
 * work happened that did not.
 */
function Pipeline({ result }) {
  const { risk, red_team: redTeam, audit, verification, remediation } = result
  const retest = remediation?.retest_metrics
  const redTeamed = risk?.requires_red_teaming === true

  const stages = [
    { name: 'Risk Triage', value: redTeamed ? 'Escalated' : 'Cleared', ran: true },
    {
      name: 'Red Team',
      value: redTeamed
        ? `${redTeam?.surfaces_flagged ?? 0} of ${redTeam?.attacks_generated ?? 0} vulnerable`
        : 'Not run',
      ran: redTeamed,
    },
    {
      name: 'Auditor',
      value: !redTeamed ? 'Not run' : audit?.violation_confirmed ? 'Violation found' : 'No violation',
      ran: redTeamed,
    },
    {
      name: 'Verifier',
      value: !redTeamed ? 'Not run' : verification?.is_supported ? 'Supported' : 'Unsupported',
      ran: redTeamed,
    },
    {
      name: 'Remediator',
      value: !redTeamed ? 'Not run' : remediation?.agent_status || 'Ran',
      ran: redTeamed,
    },
    {
      name: 'Re-Test',
      value: retest ? describeVerdict(retest.verdict).label : 'Not run',
      ran: Boolean(retest),
    },
  ]

  return (
    <ol className="grid gap-3 sm:grid-cols-3 pt-2">
      {stages.map((stage, index) => (
        <li
          key={stage.name}
          className={`border-t-2 pt-2 ${stage.ran ? 'border-slate-900' : 'border-slate-200'}`}
        >
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            {index + 1}. {stage.name}
          </p>
          <p className="mt-0.5 text-xs font-medium text-slate-800">{stage.value}</p>
        </li>
      ))}
    </ol>
  )
}

/**
 * One attack-success-rate bar. The number is printed alongside it, because bar
 * length alone is not readable at a glance or by a screen reader.
 */
function AsrBar({ label, value, tone }) {
  const width = typeof value === 'number' ? Math.max(0, Math.min(1, value)) * 100 : 0

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <span className="text-xs font-medium text-slate-600">{label}</span>
        <span className="text-xs font-semibold tabular-nums text-slate-900">{formatPercent(value)}</span>
      </div>
      <div className="mt-1 h-2 w-full rounded-full bg-slate-100 overflow-hidden">
        <div className={`h-2 rounded-full ${tone}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}

function downloadReport(result) {
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')

  link.href = url
  link.download = `reguard-audit-${result.request_id || 'report'}.json`
  link.click()
  URL.revokeObjectURL(url)
}

/**
 * Renders the response from POST /api/audit in a fixed reading order.
 * Nothing is shown that the backend did not return.
 */
export default function AuditResults({ result, originalClause }) {
  const { status, risk, audit, attack, attacks, red_team: redTeam, verification, remediation } = result
  const redTeamed = risk?.requires_red_teaming === true
  const retest = remediation?.retest_metrics
  const patchedClause = remediation?.patched_clause_text
  const statusText = describeStatus(status)

  return (
    <div className="mt-6 space-y-4">
      <div className="no-print flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Audit Report Results</h3>
        <div className="flex items-center gap-4 text-xs">
          <button
            type="button"
            onClick={() => downloadReport(result)}
            className="font-medium text-slate-700 underline decoration-slate-300 underline-offset-2 hover:text-slate-900 hover:decoration-slate-900"
          >
            Download JSON
          </button>
          <button
            type="button"
            onClick={() => window.print()}
            className="font-medium text-slate-700 underline decoration-slate-300 underline-offset-2 hover:text-slate-900 hover:decoration-slate-900"
          >
            Print / Save PDF
          </button>
        </div>
      </div>

      <Card title="Result Summary">
        <div className={`rounded border-l-4 bg-slate-50 px-4 py-3 ${statusText.border}`}>
          <p className={`text-lg font-bold tracking-tight ${statusText.color}`}>{statusText.label}</p>
          {statusText.note ? (
            <p className="mt-1 text-xs leading-relaxed text-slate-600">{statusText.note}</p>
          ) : null}
        </div>

        <div className="grid gap-4 sm:grid-cols-2 pt-2">
          <Metric
            label="Risk Category"
            value={risk?.category || '—'}
            valueClass={levelColor(risk?.category)}
          />
          <Metric label="Risk Score" value={formatPercent(risk?.risk_score)} />
        </div>

        <div className="h-1 w-full rounded-full bg-slate-100 overflow-hidden">
          <div
            className="h-1 rounded-full bg-slate-900"
            style={{ width: `${Math.min(100, (risk?.risk_score || 0) * 100)}%` }}
          />
        </div>

        <Pipeline result={result} />

        <p className="text-xs text-slate-400 font-mono pt-2">
          status <span className="text-slate-600">{status}</span>
          {` · policy #${result.policy_id}`}
          {` · clause #${result.clause_id}`}
          {result.finding_id != null ? ` · finding #${result.finding_id}` : ''}
          {result.request_id ? ` · req ${result.request_id}` : ''}
        </p>
      </Card>

      {!redTeamed ? (
        <Card title="Further Checks">
          <p className="text-xs text-slate-600">
            This clause scored below the red-team threshold, so challenger, retrieval, auditor, verifier, remediation, and re-test steps were bypassed. Only risk triage metrics are available.
          </p>
        </Card>
      ) : null}

      {redTeamed ? (
        <>
          <RedTeamCard redTeam={redTeam} attacks={attacks} attack={attack} />

          {!attack ? null : (
            <>
              <Card title="Auditor Finding">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Metric
                    label="Violation Confirmed"
                    value={audit?.violation_confirmed ? 'Yes' : 'No'}
                    valueClass={audit?.violation_confirmed ? 'text-rose-600' : 'text-emerald-700'}
                  />
                  <Metric
                    label="Severity"
                    value={audit?.severity || '—'}
                    valueClass={levelColor(audit?.severity)}
                  />
                </div>
                <p className="text-xs text-slate-500 font-mono">
                  Carried attack: {attack.surface} — {attack.title}
                </p>
                <Clause label="Attack Scenario" text={attack.attack_scenario} />
                <p className="text-xs leading-relaxed text-slate-700">
                  {audit?.explanation || 'No auditor explanation was returned for this clause.'}
                </p>
              </Card>

              <EvidenceCard evidence={audit?.evidence} audit={audit} />

              <Card title="Evidence Verification">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Metric
                    label="Citation Supported"
                    value={verification?.is_supported ? 'Yes' : 'No'}
                    valueClass={verification?.is_supported ? 'text-emerald-700' : 'text-rose-600'}
                  />
                  <Metric label="Confidence Score" value={formatPercent(verification?.confidence_score)} />
                </div>
                <p className="text-xs leading-relaxed text-slate-700">
                  {verification?.verification_rationale ||
                    'No verification rationale was returned for this audit.'}
                </p>
                {!verification?.is_supported ? (
                  <p className="text-xs text-amber-700 bg-amber-50 p-2 rounded border border-amber-200">
                    Failed closed: With the citation unverified, the clause is reported rather than rewritten.
                  </p>
                ) : null}
              </Card>

              <Card title="Remediation">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Metric
                    label="Re-Test Verdict"
                    value={describeVerdict(remediation?.status).label}
                    valueClass={describeVerdict(remediation?.status).color}
                  />
                  <Metric label="Remediator Status" value={remediation?.agent_status || '—'} />
                </div>
                <p className="text-xs leading-relaxed text-slate-700">
                  {remediation?.remediation_rationale ||
                    'No remediation rationale was returned for this audit.'}
                </p>

                <div className="grid gap-4 sm:grid-cols-2 pt-2">
                  <Clause label="Original Clause" text={originalClause} />
                  <Clause label="Patched Clause" text={patchedClause || originalClause} highlight />
                </div>

                {patchedClause === originalClause ? (
                  <p className="text-xs text-slate-500">
                    No rewrite was applied to this clause, so both versions are identical.
                  </p>
                ) : null}
              </Card>

              <ReTestCard retest={retest} />
            </>
          )}
        </>
      ) : null}
    </div>
  )
}
