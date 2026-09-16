// Small helpers for displaying the backend result.

/** 0.4832 -> "48.3%" */
export function formatPercent(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—'
  return `${Math.round(value * 1000) / 10}%`
}

/** Change in attack success rate, in percentage points. */
export function formatDelta(before, after) {
  if (typeof before !== 'number' || typeof after !== 'number') return '—'
  const delta = Math.round((after - before) * 1000) / 10
  if (delta === 0) return '0 points'
  return delta < 0 ? `${Math.abs(delta)} points lower` : `${delta} points higher`
}

export function deltaIsImprovement(before, after) {
  return typeof before === 'number' && typeof after === 'number' && after < before
}

/** Colour for a risk category or severity string. */
export function levelColor(value) {
  const text = String(value || '').toLowerCase()
  if (text.includes('high')) return 'text-red-600'
  if (text.includes('medium')) return 'text-amber-600'
  if (text.includes('low')) return 'text-green-700'
  return 'text-slate-600'
}

/** Plain-language description of the status code returned by the API. */
export function describeStatus(status) {
  switch (status) {
    case 'compliant':
      return {
        label: 'Compliant',
        color: 'text-green-700',
        note: 'Risk triage scored this clause below the red-team threshold, so the adversarial audit was not run.',
      }
    case 'remediated':
      return {
        label: 'Violation found and remediated',
        color: 'text-green-700',
        note: 'A violation was confirmed, the clause was rewritten, and the patched version passed the re-test.',
      }
    case 'remediation_flagged':
      return {
        label: 'Violation found — patch needs review',
        color: 'text-amber-600',
        note: 'A violation was confirmed and a patch was drafted, but the patch still failed at least one attack probe.',
      }
    case 'flagged_unverified':
      return {
        label: 'Flagged — evidence could not be verified',
        color: 'text-red-600',
        note: 'The verifier could not confirm the RBI citation, so remediation was skipped and the finding is left for manual review.',
      }
    case 'no_vulnerability_detected':
      return {
        label: 'No vulnerability found',
        color: 'text-green-700',
        note: 'Every red-team surface came back clear, so there was nothing to audit or remediate.',
      }
    default:
      return { label: status || 'Completed', color: 'text-slate-700', note: '' }
  }
}

/** Plain-language description of the re-test verdict. */
export function describeVerdict(verdict) {
  switch (verdict) {
    case 'fully_mitigated':
      return { label: 'Fully mitigated', color: 'text-green-700' }
    case 'partially_mitigated':
      return { label: 'Partially mitigated', color: 'text-amber-600' }
    case 'not_mitigated':
      return { label: 'Not mitigated', color: 'text-red-600' }
    case 'no_vulnerability_detected':
      return { label: 'Never vulnerable', color: 'text-slate-600' }
    case 'not_measured':
      return { label: 'Not measured', color: 'text-slate-600' }
    case 'flagged_unverified':
      return { label: 'Flagged — not remediated', color: 'text-red-600' }
    default:
      return { label: verdict || '—', color: 'text-slate-600' }
  }
}

/** Plain-language description of the red team's agreement. */
export function describeConsensus(consensus) {
  switch (consensus) {
    case 'unanimous_vulnerable':
      return 'Every surface found a way to attack this clause.'
    case 'unanimous_clear':
      return 'Every surface judged this clause clear.'
    case 'split':
      return 'The surfaces disagreed, which is the case worth a human look.'
    case 'no_attacks':
      return 'No attack agents ran for this clause.'
    default:
      return ''
  }
}
