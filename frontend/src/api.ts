export type RecoveryDna = {
  customer_id: string
  payment_method_success_by_method: Record<string, number>
  payment_success: Record<string, number>
  channel_success_by_channel: Record<string, number>
  recovery_success_by_action: Record<string, number>
  recovery_success: Record<string, number>
  average_recovery_time: number
  average_attempts_before_recovery: number
  best_recovery_hour: number | null
  best_recovery_day: string | null
  preferred_language: string | null
  preferred_channel: string | null
  preferred_payment_method: string | null
  average_invoice_delay: number
  promise_to_pay_reliability: number
  historical_opt_out_rate: number
  recovery_fatigue_score: number
  recovery_fatigue: 'LOW' | 'MEDIUM' | 'HIGH'
  lifetime_recovered_amount: number
  lifetime_at_risk_amount: number
  last_successful_recovery: string | null
  last_failed_recovery: string | null
  recovery_confidence: number
}

const apiBaseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type RadarOpportunity = {
  reason: string
  risk_score: number
  amount_at_risk: number
  confidence: number
  root_cause_candidate: string
  time_to_intervene: string
  recommended_action: string
  revenue_risk_index: number
  details: Record<string, unknown>
}

export type Radar = {
  total_revenue_at_risk: number
  high_risk_revenue: number
  medium_risk_revenue: number
  low_risk_revenue: number
  top_risk_events: RadarOpportunity[]
  risk_by_reason: Record<string, number>
  risk_by_segment: Record<string, number>
  risk_by_payment_method: Record<string, number>
  risk_trend: { direction: string; failure_rate: number; baseline_failure_rate: number; window_days: number; anchor: string }
}

export type Customer = { id: string; external_id?: string | null; name?: string | null; email?: string | null; segment?: string | null }
export type PromiseRecord = { id: string; customer_id: string; amount: number; promised_for: string; language: string; confidence: number; status: string; reminder_status?: string }
export type AuditRecord = { id: string; action: string; actor: string; details: Record<string, unknown>; created_at: string }
export type Performance = Record<string, { model_version: string; metrics: Record<string, unknown>; metadata: Record<string, unknown> }>
export type Twin = { baseline_at_risk: number; organic_recovery: number; assisted_recovery: number; incremental_recovery: number; recovery_rate_without_dhanrakshak: number; recovery_rate_with_dhanrakshak: number; confidence: number; sample_size: number }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) } })
  } catch {
    throw new Error('API_UNREACHABLE')
  }
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(detail || `API_${response.status}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string; service: string }>('/health'),
  getRadar: () => request<Radar>('/api/v1/revenue-at-risk'),
  getRecovered: () => request<{ total_recovered: number; verified_outcomes: number }>('/api/v1/revenue-recovered'),
  getCustomers: (limit = 100) => request<{ items: Customer[]; total: number }>(`/api/v1/customers?limit=${limit}`),
  getCustomer: (id: string) => request<Customer>(`/api/v1/customers/${encodeURIComponent(id)}`),
  getRecoveryDna: (id: string) => request<RecoveryDna>(`/api/v1/customers/${encodeURIComponent(id)}/recovery-dna`),
  getPromises: () => request<{ items: PromiseRecord[] }>('/api/v1/promises-to-pay'),
  createPromise: (customer_id: string, text: string, amount?: number) => request<PromiseRecord>('/api/v1/promises-to-pay', { method: 'POST', body: JSON.stringify({ customer_id, text, ...(amount ? { amount } : {}) }) }),
  getExperiments: () => request<{ items: Record<string, unknown>[] }>('/api/v1/experiments'),
  createExperiment: (payload: { name: string; configuration: Record<string, unknown>; active: boolean }) => request<Record<string, unknown>>('/api/v1/experiments', { method: 'POST', body: JSON.stringify(payload) }),
  getAudit: () => request<{ items: AuditRecord[] }>('/api/v1/audit'),
  getPerformance: () => request<Performance>('/api/v1/models/performance'),
  getTwin: () => request<Twin>('/api/v1/recovery-twin/simulate', { method: 'POST', body: '{}' }),
  getDemoStatus: () => request<{ status: string; data: Record<string, unknown> }>('/api/v1/demo/status'),
  resetDemo: () => request<{ status: string; data: Record<string, unknown> }>('/api/v1/demo/reset', { method: 'POST', body: '{}' }),
  runDemo: () => request<{ status: string; data: Record<string, unknown> }>('/api/v1/demo/run', { method: 'POST', body: '{}' }),
  analyzeRootCause: (customer_id: string) => request<Record<string, unknown>>('/api/v1/root-cause/analyze', { method: 'POST', body: JSON.stringify({ customer_id }) }),
  simulateRecovery: (customer_id: string, amount: number, payment_method = 'upi') => request<{ actions: Record<string, unknown>[] }>('/api/v1/recovery/simulate', { method: 'POST', body: JSON.stringify({ customer_id, amount, payment_method }) }),
}

