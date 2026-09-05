/** Thin fetch wrapper over the FastAPI surface. */

import { type Scope, tokenFor } from "./auth";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

async function request<T>(
  path: string,
  scope: Scope,
  init: RequestInit = {},
): Promise<T> {
  const token = tokenFor(scope);
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? body.error ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, String(detail));
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  get: <T>(p: string, s: Scope = "internal") => request<T>(p, s),
  post: <T>(p: string, body?: unknown, s: Scope = "internal") =>
    request<T>(p, s, { method: "POST", body: JSON.stringify(body ?? {}) }),
  patch: <T>(p: string, body?: unknown, s: Scope = "internal") =>
    request<T>(p, s, { method: "PATCH", body: JSON.stringify(body ?? {}) }),
  del: <T>(p: string, s: Scope = "internal") =>
    request<T>(p, s, { method: "DELETE" }),
};

// ---------------------------------------------------------------- types

export interface Line {
  id: number;
  product_id: number;
  product_name: string;
  category: string;
  qty: number;
  unit_price: string;
  discount_pct: string;
  ceiling_pct_applied: string | null;
  margin_pct: string | null;
  is_recurring: boolean;
  list_value: string;
  net_value: string;
  excess_pp: string;
  breaches_ceiling: boolean;
}

export interface ApprovalStep {
  id: number;
  step_index: number;
  approver_role: string;
  decision: string;
  reason: string | null;
  decided_by: number | null;
  decided_at: string | null;
}

export interface Quote {
  id: number;
  customer_id: number;
  customer_name: string;
  customer_tier: string;
  rep_id: number;
  state: string;
  version: number;
  risk_score: string | null;
  lines: Line[];
  approval_steps: ApprovalStep[];
  legal_events: string[];
  totals: Record<string, string | number>;
}

export interface Score {
  quotation_id: number;
  state: string;
  version: number;
  score: number;
  approval_chain: string[];
  hard_stop: boolean;
  components: Record<string, number>;
  aggregates: Record<string, number>;
  explanation: string[];
  verifier_verdict: string;
  verifier_reasons: string[];
}

export interface Customer {
  id: number;
  name: string;
  tier: string;
  is_new: boolean;
}

export interface Product {
  id: number;
  sku: string;
  name: string;
  category: string;
  list_price: string;
  is_subscription: boolean;
  is_promoted: boolean;
}

export interface Policy {
  tier: string;
  category: string;
  ceiling_pct: string;
  floor_margin_pct: string;
}

export interface Suggestion {
  product_id: number;
  sku: string;
  name: string;
  category: string;
  score: number;
  lift: number;
  confidence: number;
  is_promoted: boolean;
  has_stock: boolean;
  current_margin_pct: number;
  projected_margin_pct: number;
  margin_delta_if_added: number;
  list_price: string;
  because_of: string;
}

export interface SuggestionsOut {
  quotation_id: number;
  suggestions: Suggestion[];
  considered: number;
  dropped: string[];
  tier: number;
}

export interface FulfillmentLine {
  product_id: number;
  product_name: string;
  warehouse: string | null;
  qty: number;
  is_backorder: boolean;
}

export interface FulfillmentOut {
  quotation_id: number;
  plan: { id: number; total_cost: string; shipment_count: number } | null;
  lines: FulfillmentLine[];
}

export interface InvoiceOut {
  id: number;
  kind: string;
  total: string;
  status: string;
  period_key: string | null;
  lines: { description: string; qty: number; unit_price: string; amount: string }[];
  credit_notes: { amount: string; reason: string }[];
  payments: { amount: string; method: string }[];
}

export interface InvoicesOut {
  quotation_id: number;
  invoices: InvoiceOut[];
  subscription: {
    id: number;
    start_date: string;
    next_bill_date: string;
    status: string;
  } | null;
}

export interface AmountDue {
  billed: string;
  credited: string;
  amount_due: string;
  paid: string;
  outstanding: string;
}

export interface PortalQuoteSummary {
  id: number;
  state: string;
  line_count: number;
  net_total: string;
}

export interface PortalLine {
  id: number;
  product_name: string;
  category: string;
  qty: number;
  unit_price: string;
  discount_pct: string;
  net_value: string;
}

export interface PortalQuoteDetail {
  id: number;
  customer_name: string;
  state: string;
  version: number;
  lines: PortalLine[];
  net_total: string;
}

export interface PortalMessage {
  id: number;
  author_name: string;
  body: string;
  quote_line_id: number | null;
  counter_discount_pct: string | null;
  created_at: string;
}

export interface DealHealthAssessment {
  quotation_id: number;
  customer_id: number;
  customer_name: string;
  customer_tier: string;
  rep_id: number;
  rep_name: string;
  state: string;
  version: number;
  alert: boolean;
  stalled: boolean;
  discount_anomaly: boolean;
  robust_z: number;
  history_source: string;
  delivery_slippage: boolean;
  isolation_forest_outlier: boolean;
  votes: number;
  explanation: string[];
  last_activity_at: string;
  days_inactive: number;
  discount_pct: number;
}

export interface RepPerformance {
  rep_id: number;
  rep_name: string;
  quote_count: number;
  total_net: string;
  avg_discount_pct: number;
}

export interface CategoryBreakdown {
  category: string;
  units: number;
  net_revenue: string;
}

export interface ReportingMetrics {
  period: string;
  total_quotes: number;
  total_pipeline_value: string;
  total_list_value: string;
  total_discount_savings: string;
  avg_discount_pct: number;
  conversion_rate_pct: number;
  status_distribution: Record<string, number>;
  rep_performance: RepPerformance[];
  category_breakdown: CategoryBreakdown[];
}

export interface ReliabilityStats {
  total_invocations: number;
  pass_rate_pct: number;
  avg_latency_ms: number;
  max_latency_ms: number;
  invocations_by_agent: Record<string, number>;
  verifier_verdicts: Record<string, number>;
  latency_by_agent: Record<string, number>;
}

export interface DecisionLogRow {
  id: number;
  agent: string;
  engine_version: string;
  quotation_id: number | null;
  input_hash: string;
  input_json: any;
  output_json: any;
  verifier_verdict: string;
  latency_ms: number;
  created_at: string;
}

export interface ReplayResult {
  log_id: number;
  agent: string;
  engine_version: string;
  input_hash: string;
  input_hash_matches: boolean;
  output_matches: boolean;
  reproduced: boolean;
  replayed_output: any;
}
