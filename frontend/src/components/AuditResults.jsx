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
    <section className="rounded-lg border border-slate-200 bg-white p-6">
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
      {subtitle ? <p className="mt-1 text-xs text-slate-500">{subtitle}</p> : null}
      <div className="mt-4 space-y-4 text-sm text-slate-700">{children}</div>
    </section>
  )
}

function Label({ children }) {
  return (
    <span className="text-xs font-medium tracking-wide text-slate-500 uppercase">{children}</span>
  )
}

function Metric({ label, value, valueClass = 'text-slate-900' }) {
  return (
    <div>
      <Label>{label}</Label>
      <div className={`mt-1 text-xl font-semibold ${valueClass}`}>{value}</div>
    </div>
  )
}

function Clause({ label, text, highlight = false }) {
  return (
    <div
      className={`rounded-md border p-4 ${
        highlight ? 'border-blue-200 bg-blue-50/50' : 'border-slate-200 bg-slate-50'
      }`}
    >
      <Label>{label}</Label>
      <p className="mt-2 leading-relaxed text-slate-700">{text || '—'}</p>
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
      title="Red team"
      subtitle={`${redTeam.attacks_generated} specialised agents, run in parallel`}
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <Metric label="Surfaces flagged" value={`${redTeam.surfaces_flagged} / ${redTeam.attacks_generated}`} />
        <Metric label="Agreement" value={formatPercent(redTeam.agreement)} />
        <Metric
          label="Highest severity"
          value={redTeam.highest_severity || '—'}
          valueClass={levelColor(redTeam.highest_severity)}
        />
      </div>

      <p className="text-slate-600">{describeConsensus(redTeam.consensus)}</p>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              {['Surface', 'Verdict', 'Severity', 'Status'].map((cell) => (
                <th key={cell} className="py-2 pr-4 text-xs font-medium tracking-wide text-slate-500 uppercase">
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(attacks || []).map((item) => (
              <tr key={item.surface} className="border-b border-slate-100 last:border-0">
                <td className="py-2 pr-4">{item.title || item.surface}</td>
                <td className={`py-2 pr-4 ${item.vulnerability_detected ? 'text-red-600' : 'text-green-700'}`}>
                  {item.vulnerability_detected ? 'Vulnerable' : 'Clear'}
                </td>
                <td className={`py-2 pr-4 ${levelColor(item.severity)}`}>{item.severity}</td>
                <td className="py-2 pr-4 text-slate-500">
                  {item.failed
                    ? 'Agent failed — treated as not cleared'
                    : item.surface === attack?.surface
                      ? 'Carried into the audit'
                      : 'Reported only'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {redTeam.failed_surfaces?.length ? (
        <p className="text-xs text-amber-600">
          {redTeam.failed_surfaces.join(', ')} did not return a verdict, so those surfaces were not
          cleared.
        </p>
      ) : null}
    </Card>
  )
}

/** Where the decision came from: document, page, section and the runners-up. */
function EvidenceCard({ evidence, audit }) {
  if (!evidence || !evidence.citation) {
    return (
      <Card title="Regulatory evidence">
        <p className="rounded-md border border-slate-200 bg-slate-50 p-4 leading-relaxed">
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

  return (
    <Card title="Regulatory evidence" subtitle={evidence.citation}>
      <div className="grid gap-4 sm:grid-cols-3">
        <Metric label="Passage id" value={evidence.passage_id || '—'} />
        <Metric label="Section" value={evidence.section || '—'} />
        <Metric label="Status" value={currency.status || '—'} />
      </div>

      <div>
        <Label>Cited passage</Label>
        <p className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-4 leading-relaxed">
          {evidence.passage_text || audit?.retrieved_passage || '—'}
        </p>
      </div>

      <p className="text-xs text-slate-500">
        Effective date{' '}
        <span className="font-mono">{currency.effective_date || 'not recorded in the corpus'}</span>
        {typeof currency.age_days === 'number' ? ` · ${currency.age_days} days old as of ${currency.as_of}` : ''}
      </p>

      {otherWarnings.length ? (
        <ul className="list-disc space-y-1 pl-5 text-xs text-amber-700">
          {otherWarnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}

      {evidence.candidates?.length ? (
        <div>
          <Label>Also retrieved</Label>
          <ul className="mt-2 space-y-2">
            {evidence.candidates.map((candidate, index) => (
              <li key={`${candidate.citation}-${index}`} className="rounded-md border border-slate-200 p-3">
                <p className="text-xs text-slate-500">
                  <span className="font-mono">{candidate.citation || candidate.document}</span>
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

// An attack outcome is true (defeated the clause), false (blocked), or null
// (the call failed and it was never measured). Null is not "blocked".
function outcomeLabel(outcome) {
  if (outcome === null || outcome === undefined) return 'Not measured'
  return outcome ? 'Defeated' : 'Blocked'
}

function outcomeClass(outcome) {
  if (outcome === null || outcome === undefined) return 'text-slate-500'
  return outcome ? 'text-red-600' : 'text-green-700'
}

/** ASR before and after, measured over the same attack set both times. */
function ReTestCard({ retest }) {
  if (!retest) {
    return (
      <Card title="Attack success rate (re-test)">
        <p className="text-slate-600">
          No re-test metrics were returned for this audit, so no ASR values are shown.
        </p>
      </Card>
    )
  }

  const verdict = describeVerdict(retest.verdict)

  return (
    <Card
      title="Attack success rate (re-test)"
      subtitle={`ASR is the share of the same ${retest.total_attacks} attacks that defeated the clause before and after the patch`}
    >
      <div className="grid gap-4 sm:grid-cols-4">
        <Metric label="ASR before" value={formatPercent(retest.asr_before)} valueClass="text-red-600" />
        <Metric
          label="ASR after"
          value={formatPercent(retest.asr_after)}
          valueClass={retest.asr_after === 0 ? 'text-green-700' : 'text-amber-600'}
        />
        <Metric
          label="Change"
          value={formatDelta(retest.asr_before, retest.asr_after)}
          valueClass={
            deltaIsImprovement(retest.asr_before, retest.asr_after) ? 'text-green-700' : 'text-red-600'
          }
        />
        <Metric label="Verdict" value={verdict.label} valueClass={verdict.color} />
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Metric label="Attacks run" value={retest.total_attacks ?? '—'} />
        <Metric label="Defeated before" value={retest.original_successes ?? '—'} valueClass="text-red-600" />
        <Metric
          label="Defeated after"
          value={retest.patched_successes ?? '—'}
          valueClass={retest.patched_successes === 0 ? 'text-green-700' : 'text-amber-600'}
        />
        <Metric
          label="Exploits blocked by the patch"
          value={
            retest.remediation_success_rate == null
              ? 'n/a'
              : formatPercent(retest.remediation_success_rate)
          }
        />
      </div>

      <p className="text-xs text-slate-500">
        {retest.verdict === 'no_vulnerability_detected'
          ? 'No attack succeeded even before the patch, so the re-test cannot demonstrate a fix.'
          : 'Only a clean sweep counts as fully mitigated; a partial reduction is reported as partial.'}
      </p>

      {retest.measurement_complete === false ? (
        <p className="text-xs text-amber-700">
          {retest.unmeasured_attacks} of {retest.total_attacks} attacks could not be measured, so the
          rates above cover the {retest.measured_attacks} that were. A failed model call is not
          counted as a blocked attack, and this re-test is not reported as passed.
        </p>
      ) : null}

      {retest.per_attack?.length ? (
        <div className="overflow-x-auto">
          <Label>Per attack</Label>
          <table className="mt-2 w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200">
                {['Surface', 'Before', 'After', 'Outcome'].map((cell) => (
                  <th key={cell} className="py-2 pr-4 text-xs font-medium tracking-wide text-slate-500 uppercase">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {retest.per_attack.map((row) => (
                <tr key={row.surface} className="border-b border-slate-100 last:border-0">
                  <td className="py-2 pr-4">{row.title || row.surface}</td>
                  <td className={`py-2 pr-4 ${outcomeClass(row.succeeded_before)}`}>
                    {outcomeLabel(row.succeeded_before)}
                  </td>
                  <td className={`py-2 pr-4 ${outcomeClass(row.succeeded_after)}`}>
                    {outcomeLabel(row.succeeded_after)}
                  </td>
                  <td className="py-2 pr-4 text-slate-500">
                    {!row.measured
                      ? 'Not measured'
                      : row.blocked_by_patch
                        ? 'Closed by the patch'
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
    <div className="mt-8 space-y-5">
      <Card title="Result summary">
        <div>
          <p className={`text-lg font-semibold ${statusText.color}`}>{statusText.label}</p>
          {statusText.note ? <p className="mt-1 text-slate-600">{statusText.note}</p> : null}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Metric
            label="Risk category"
            value={risk?.category || '—'}
            valueClass={levelColor(risk?.category)}
          />
          <Metric label="Risk score" value={formatPercent(risk?.risk_score)} />
        </div>

        <div className="h-1.5 w-full rounded-full bg-slate-100">
          <div
            className="h-1.5 rounded-full bg-blue-600"
            style={{ width: `${Math.min(100, (risk?.risk_score || 0) * 100)}%` }}
          />
        </div>

        <p className="text-xs text-slate-500">
          status <span className="font-mono">{status}</span>
          {` · policy #${result.policy_id}`}
          {` · clause #${result.clause_id}`}
          {result.finding_id != null ? ` · finding #${result.finding_id}` : ''}
          {result.request_id ? (
            <>
              {' · request '}
              <span className="font-mono">{result.request_id}</span>
            </>
          ) : null}
        </p>
      </Card>

      {!redTeamed ? (
        <Card title="Further checks">
          <p className="text-slate-600">
            This clause scored below the red-team threshold, so the challenger, retrieval, auditor,
            verifier, remediation and re-test steps were not run. Only the risk triage result is
            available.
          </p>
        </Card>
      ) : null}

      {redTeamed ? (
        <>
          <RedTeamCard redTeam={redTeam} attacks={attacks} attack={attack} />

          {!attack ? null : (
            <>
              <Card title="Auditor finding">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Metric
                    label="Violation confirmed"
                    value={audit?.violation_confirmed ? 'Yes' : 'No'}
                    valueClass={audit?.violation_confirmed ? 'text-red-600' : 'text-green-700'}
                  />
                  <Metric
                    label="Severity"
                    value={audit?.severity || '—'}
                    valueClass={levelColor(audit?.severity)}
                  />
                </div>
                <p className="text-xs text-slate-500">
                  Attack carried into the audit: {attack.surface} — {attack.title}
                </p>
                <Clause label="Attack scenario" text={attack.attack_scenario} />
                <p className="leading-relaxed">
                  {audit?.explanation || 'No auditor explanation was returned for this clause.'}
                </p>
              </Card>

              <EvidenceCard evidence={audit?.evidence} audit={audit} />

              <Card title="Evidence verification">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Metric
                    label="Citation supported"
                    value={verification?.is_supported ? 'Yes' : 'No'}
                    valueClass={verification?.is_supported ? 'text-green-700' : 'text-red-600'}
                  />
                  <Metric label="Confidence" value={formatPercent(verification?.confidence_score)} />
                </div>
                <p className="leading-relaxed">
                  {verification?.verification_rationale ||
                    'No verification rationale was returned for this audit.'}
                </p>
                {!verification?.is_supported ? (
                  <p className="text-xs text-slate-500">
                    Failed closed: with the citation unverified, the clause is reported rather than
                    rewritten.
                  </p>
                ) : null}
              </Card>

              <Card title="Remediation">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Metric
                    label="Re-test verdict (did the patch work)"
                    value={describeVerdict(remediation?.status).label}
                    valueClass={describeVerdict(remediation?.status).color}
                  />
                  <Metric label="Remediator agent's own status" value={remediation?.agent_status || '—'} />
                </div>
                <p className="leading-relaxed">
                  {remediation?.remediation_rationale ||
                    'No remediation rationale was returned for this audit.'}
                </p>

                <div className="grid gap-4 sm:grid-cols-2">
                  <Clause label="Original clause" text={originalClause} />
                  <Clause label="Patched clause" text={patchedClause || originalClause} highlight />
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
