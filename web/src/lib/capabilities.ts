import { useEffect, useState } from "react";
import { api } from "./api";
import { tokenFor, type Scope } from "./auth";

/**
 * What the signed-in user may do, as decided by the server.
 *
 * The list comes from app/domain/capabilities.py so the navigation a user sees
 * and the endpoints they may call are one definition. A frontend that decides
 * for itself which role gets which button drifts from the API, and the drift
 * only shows up when somebody clicks.
 *
 * Hiding a control is presentation, not security — every endpoint still applies
 * its own role guard server-side.
 */
export type Capability =
  | "build_quote" | "view_quotes" | "edit_quote_lines" | "send_to_portal"
  | "view_suggestions" | "view_approvals" | "approve_manager_step"
  | "approve_finance_step" | "configure_discounts" | "view_fulfillment"
  | "plan_fulfillment" | "override_fulfillment" | "view_invoices"
  | "record_payment" | "manage_subscriptions" | "view_deal_health"
  | "view_reports" | "view_audit_log" | "manage_catalog"
  | "portal_view_quotes" | "portal_negotiate" | "portal_confirm"
  | "portal_view_profile";

export interface Me {
  user_id: number;
  email: string;
  full_name: string;
  role: string;
  scope: string;
  capabilities: Capability[];
  customer?: { id: number; name: string; tier: string };
}

export function useMe(scope: Scope = "internal") {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  // Keyed on the token, not just the scope. The routers call this on mount,
  // which happens while the user is still signed out — that request 401s, and
  // with `[scope]` deps nothing ever asked again, so capabilities stayed empty
  // for the rest of the session. Signing in changes the token, which re-runs
  // this; signing out clears it, which drops `me` back to null.
  const token = tokenFor(scope);

  useEffect(() => {
    if (!token) { setMe(null); setLoading(false); return; }
    let alive = true;
    setLoading(true);
    api.get<Me>("/api/me", scope)
      .then((m) => { if (alive) setMe(m); })
      .catch(() => { if (alive) setMe(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [scope, token]);

  const can = (c: Capability) => !!me?.capabilities.includes(c);
  return { me, loading, can };
}
