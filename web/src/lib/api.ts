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
  put: <T>(p: string, body?: unknown, s: Scope = "internal") =>
    request<T>(p, s, { method: "PUT", body: JSON.stringify(body ?? {}) }),
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
  decided_by_name: string | null;
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
  current_stage: string | null;
  risk_band: string | null;
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
  /** null when no verifier has judged any call yet — render as "not measured",
   *  never as success. See services/reliability.py. */
  total_invocations: number;
  pass_rate_pct: number | null;
  verified_calls: number;
  skipped_calls: number;
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

// ---------------------------------------------------------------- screen 2
export interface DashboardOut {
  role: string;
  full_name: string;
  cards: {
    pending_approvals: number;
    open_quotations: number;
    at_risk_deals: number;
    awaiting_fulfillment: number;
    unpaid_invoices: number;
  };
  at_risk: {
    quotation_id: number;
    customer_name: string;
    state: string;
    days_inactive: number;
    reason: string;
  }[];
  recent_activity: {
    quotation_id: number;
    customer_name: string;
    state: string;
    rep_name: string;
    risk_score: string | null;
    last_activity_at: string;
  }[];
}

// ---------------------------------------------------------------- screen 7
export interface StockRow {
  warehouse: string;
  warehouse_id: number;
  warehouse_name: string;
  product_id: number;
  sku: string;
  product_name: string;
  category: string;
  qty_on_hand: number;
  qty_reserved: number;
  qty_available: number;
}

export interface PendingOrder {
  quotation_id: number;
  customer_name: string;
  state: string;
  planned: boolean;
  status: string;
  warehouses: string[];
  shipment_count: number;
  net_total: string;
}

// ---------------------------------------------------------------- screen 9
export interface SubscriptionRow {
  id: number;
  quotation_id: number;
  customer_name: string;
  customer_tier: string;
  plan: string;
  cycle: string;
  start_date: string;
  next_bill_date: string;
  status: string;
  amount: string;
}

// ------------------------------------------------------------ screens 12/13
export interface InvoiceRow {
  id: number;
  reference: string;
  quotation_id: number;
  customer_name: string;
  kind: string;
  total: string;
  paid: string;
  credited: string;
  outstanding: string;
  status: string;
  period_key: string | null;
  subscription_id: number | null;
  issued_at: string | null;
}

export interface InvoiceDetailOut extends InvoiceRow {
  tracker: { step: string; done: boolean }[];
  lines: { description: string; qty: number; unit_price: string; amount: string }[];
  credit_notes: { amount: string; reason: string }[];
  payments: { amount: string; method: string; paid_at: string }[];
  quotation_state: string | null;
}

// ----------------------------------------------------------- screens 16/17
export interface CatalogSummary {
  total_products: number;
  subscription_products: number;
  price_lists: number;
  currencies: string[];
  variants: number;
}

export interface CatalogProduct {
  id: number;
  sku: string;
  name: string;
  category: string;
  list_price: string;
  unit_cost: string;
  margin_pct: string;
  is_subscription: boolean;
  is_promoted: boolean;
  variants: number;
  qty_available: number;
}

export interface ProductDetailOut {
  id: number;
  sku: string;
  name: string;
  category: string;
  list_price: string;
  unit_cost: string;
  is_subscription: boolean;
  is_promoted: boolean;
  recurring_interval: string | null;
  qty_on_hand: number;
  qty_reserved: number;
  variants: { attribute: string; values: { value: string; extra_price: string }[] }[];
  price_lists: { name: string; currency: string; price: string }[];
}

// --------------------------------------------------------------- screen 18
export interface DiscountConfig {
  tier_ceilings: { tier: string; ceiling_pct: string }[];
  category_ceilings: {
    tier: string;
    category: string;
    ceiling_pct: string;
    floor_margin_pct: string;
    effective_pct: string;
  }[];
  approval_chains: {
    min_score: string;
    max_score: string;
    steps: string[];
    label: string;
  }[];
  engine_thresholds: {
    route_manager_min: string;
    route_finance_min: string;
    hard_stop_excess_pp: string;
  };
}

export interface BillingDetailOut {
  quotation_id: number;
  state: string;
  one_time_lines: { product_id: number; product_name: string; qty: number; amount: string }[];
  recurring_lines: { product_id: number; product_name: string; qty: number; amount: string }[];
  subscription: {
    id: number;
    start_date: string;
    next_bill_date: string;
    status: string;
  } | null;
}

export interface PriceListRef {
  id: number;
  name: string;
  currency: string;
}
