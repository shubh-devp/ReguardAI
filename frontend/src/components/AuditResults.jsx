import {
  deltaIsImprovement,
  describeStatus,
  formatDelta,
  formatPercent,
  levelColor,
} from '../lib/format'

function Card({ title, children }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6">
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
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
 * Renders the response from POST /api/audit in a fixed reading order.
 * Nothing is shown that the backend did not return.
 */
export default function AuditResults({ result, originalClause }) {
  const { status, risk, audit, attack, verification, remediation } = result
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
          status <span className="font-mono">{status}</span> · policy #{result.policy_id} · clause #
          {result.clause_id}
          {result.finding_id != null ? ` · finding #${result.finding_id}` : ''}
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
            <p className="leading-relaxed">
              {audit?.explanation || 'No auditor explanation was returned for this clause.'}
            </p>
          </Card>

          <Card title="Attack scenario">
            <p className="leading-relaxed">
              {attack?.attack_scenario ||
                'The challenger did not return a scenario for this clause.'}
            </p>
            {attack?.explanation ? <p className="text-slate-600">{attack.explanation}</p> : null}
            {attack && attack.vulnerability_detected != null ? (
              <p className="text-xs text-slate-500">
                Vulnerability detected:{' '}
                <span className={attack.vulnerability_detected ? 'text-red-600' : 'text-green-700'}>
                  {attack.vulnerability_detected ? 'yes' : 'no'}
                </span>
                {attack.severity ? ` · challenger severity: ${attack.severity}` : ''}
              </p>
            ) : null}
          </Card>

          <Card title="RBI regulatory evidence">
            <p className="rounded-md border border-slate-200 bg-slate-50 p-4 leading-relaxed">
              {audit?.retrieved_passage || 'No statutory passage was returned for this audit.'}
            </p>
            <p className="text-xs text-slate-500">
              Reference <span className="font-mono">{audit?.matched_rbi_passage_id || '—'}</span>
            </p>
          </Card>

          <Card title="Evidence verification">
            <div className="grid gap-4 sm:grid-cols-2">
              <Metric
                label="Citation supported"
                value={verification?.is_supported ? 'Yes' : 'No'}
                valueClass={verification?.is_supported ? 'text-green-700' : 'text-red-600'}
              />
              <Metric
                label="Confidence"
                value={formatPercent(verification?.confidence_score)}
              />
            </div>
            <p className="leading-relaxed">
              {verification?.verification_rationale ||
                'No verification rationale was returned for this audit.'}
            </p>
          </Card>

          <Card title="Remediation">
            <Metric label="Remediation status (remediator agent)" value={remediation?.status || '—'} />
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

          <Card title="ASR before vs after">
            {retest ? (
              <>
                <div className="grid gap-4 sm:grid-cols-3">
                  <Metric
                    label="ASR before"
                    value={formatPercent(retest.asr_before)}
                    valueClass="text-red-600"
                  />
                  <Metric
                    label="ASR after"
                    value={formatPercent(retest.asr_after)}
                    valueClass={retest.asr_after === 0 ? 'text-green-700' : 'text-amber-600'}
                  />
                  <Metric
                    label="Change"
                    value={formatDelta(retest.asr_before, retest.asr_after)}
                    valueClass={
                      deltaIsImprovement(retest.asr_before, retest.asr_after)
                        ? 'text-green-700'
                        : 'text-red-600'
                    }
                  />
                </div>
                <p className="text-xs text-slate-500">
                  Attack success rate is the share of the probe set that succeeded against the clause.
                </p>
              </>
            ) : (
              <p className="text-slate-600">
                No re-test metrics were returned for this audit, so no ASR values are shown.
              </p>
            )}
          </Card>

          <Card title="Re-test results">
            {retest ? (
              <>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Metric label="Probes" value={retest.total_attacks ?? '—'} />
                  <Metric
                    label="Succeeded before"
                    value={retest.original_successes ?? '—'}
                    valueClass="text-red-600"
                  />
                  <Metric
                    label="Succeeded after"
                    value={retest.patched_successes ?? '—'}
                    valueClass={retest.patched_successes === 0 ? 'text-green-700' : 'text-amber-600'}
                  />
                  <Metric
                    label="Outcome"
                    value={retest.retest_passed ? 'Passed' : 'Failed'}
                    valueClass={retest.retest_passed ? 'text-green-700' : 'text-red-600'}
                  />
                </div>
                <p className="text-xs text-slate-500">
                  The API returns totals for the whole probe set; the individual probes are not part
                  of the response.
                </p>
              </>
            ) : (
              <p className="text-slate-600">
                This audit did not include probe results, so nothing is listed here.
              </p>
            )}
          </Card>
        </>
      ) : null}
    </div>
  )
}
