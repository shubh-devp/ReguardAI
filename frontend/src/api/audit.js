// Client for the Reguard AI backend.
// The endpoint and request body are fixed by src/api/app.py.

const AUDIT_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api/audit'

/**
 * Sends one clause to POST /api/audit and returns the pipeline result.
 *
 * @param {{ policyName: string, clauseText: string }} audit
 */
export async function runAudit({ policyName, fullText,clauseText }) {
  let response

  try {
    response = await fetch(AUDIT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        policy_name: policyName,
        full_text: fullText || clauseText,
        clause_text: clauseText,
      }),
    })
  } catch {
    throw new Error('Could not reach the backend. Make sure the Flask server is running on port 5000.')
  }

  if (!response.ok) {
    throw new Error(`The backend returned HTTP ${response.status}.`)
  }

  return response.json()
}
