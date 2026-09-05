/** Thin fetch wrapper over the FastAPI surface. */

import { type Scope, tokenFor } from "./auth";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

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
