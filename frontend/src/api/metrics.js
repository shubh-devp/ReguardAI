// Client for GET /api/metrics.
//
// The numbers are produced by the evaluation scripts in src/evaluation and served
// straight from their result files, so the dashboard cannot show anything the
// experiments did not measure.

const METRICS_URL = (import.meta.env.VITE_API_URL || 'http://localhost:5000/api/audit').replace(
  /\/audit\/?$/,
  '/metrics',
)

export async function fetchMetrics() {
  const response = await fetch(METRICS_URL)

  if (!response.ok) {
    throw new Error(`Metrics request returned HTTP ${response.status}.`)
  }

  return response.json()
}
