const base = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '')

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${base}${path}`)
  if (!r.ok) throw new Error(`${r.status}`)
  return r.json() as Promise<T>
}
export async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${base}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(`${r.status}`)
  return r.json() as Promise<T>
}

export type ScoredCustomer = {
  customer_id: string; name: string; city: string; segment: string; language: string; lifetime_value: number
  preferred_payment_method: string; preferred_channel: string; historical_payment_success_rate: number
  historical_recovery_rate: number; risk_score: number; open_amount: number; risk_segment: string
}
export type ActionScore = { action: string; recovery_probability: number; uplift_vs_organic: number; expected_recovered_amount: number; intervention_cost: number; friction_cost: number; expected_incremental_value: number }
export type Score = {
  risk: { probability_unrecovered: number; tier: 'low' | 'medium' | 'high'; model_version: string }
  organic_recovery_probability: number; do_nothing_probability: number; estimated_organic_revenue: number; actions: ActionScore[]
  recommended_action: string; policy_decision: 'ALLOW' | 'BLOCK' | 'ESCALATE'; explanation: string
  customer?: ScoredCustomer & Record<string, unknown>
}
export type Scenario = {
  amount: number; customer_lifetime_value: number; historical_payment_success_rate: number; historical_recovery_rate: number
  retry_count: number; days_overdue: number; customer_tenure: number; days_since_last_payment: number
  payment_method: string; failure_reason: string; preferred_channel: string; segment: string; hour: number
}
export type Summary = {
  revenue_risk: { version: string; trained_at: string; training_rows: number; test_rows: number; validation: Record<string, number>; test: Record<string, number> }
  action_recovery: { version: string; trained_at: string; training_rows: number; per_action_auc: Record<string, number> }
  incrementality: { version: string; trained_at: string; training_rows: number; control_recovery_rate: number; treatment_recovery_rate: number; uplift: number; incremental_recovered_revenue: number; test_treatment_rows: number; test_control_rows: number }
  dataset_version: string
}
export type Twin = { baseline_at_risk: number; organic_recovery: number; assisted_recovery: number; incremental_recovery: number; recovery_rate_without_dhanrakshak: number; recovery_rate_with_dhanrakshak: number; sample_size: number }
export type RadarLite = { total_revenue_at_risk: number; high_risk_revenue: number; medium_risk_revenue: number; low_risk_revenue: number; risk_by_reason: Record<string, number>; top_risk_events: { reason: string; amount_at_risk: number; risk_score: number; recommended_action: string; time_to_intervene: string }[] }

export const inr = (v?: number | null, compact = false) => {
  if (v == null || Number.isNaN(v)) return '—'
  if (compact && Math.abs(v) >= 1e7) return `₹${(v / 1e7).toLocaleString('en-IN', { maximumFractionDigits: 2 })} Cr`
  if (compact && Math.abs(v) >= 1e5) return `₹${(v / 1e5).toLocaleString('en-IN', { maximumFractionDigits: 1 })} L`
  return `₹${Math.round(v).toLocaleString('en-IN')}`
}
export const pct = (v?: number | null, d = 1) => v == null || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(d)}%`
export const label = (s: string) => s.replaceAll('_', ' ')

/** risk 0..1 → colour from jade through saffron to vermilion */
export function riskColor(r: number): string {
  const t = Math.min(1, Math.max(0, (r - 0.25) / 0.6))
  const stops = [[56, 214, 176], [244, 183, 64], [240, 76, 62]]
  const [a, b, k] = t < 0.5 ? [stops[0], stops[1], t * 2] : [stops[1], stops[2], (t - 0.5) * 2]
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * k))
  return `rgb(${c[0]},${c[1]},${c[2]})`
}
