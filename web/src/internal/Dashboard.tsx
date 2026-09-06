
import { Link } from "react-router-dom";
import { api, type DashboardOut } from "@/lib/api";
import { ErrorBanner, PageHeader, StatCard, StateBadge } from "./components";
import { useLiveData } from "@/lib/live";
import { useMe } from "@/lib/capabilities";

export default function Dashboard() {
  // Same capability the nav uses. A rep has no view_approvals, so this button
  // led them to a screen the API refuses.
  const { can } = useMe("internal");
  // Live: approvals land, deals stall and invoices are paid while this screen
  // is open. A fetch on mount alone leaves the landing page quietly stale.
  const { data, error, initialLoading, lastUpdated } = useLiveData<DashboardOut>(
    () => api.get<DashboardOut>("/api/dashboard"),
  );

  // Keep the last good data on screen if a refresh fails — blanking a working
  // dashboard because one poll errored is worse than showing slightly old rows.
  if (error && !data) return <ErrorBanner error={error} />;
  if (initialLoading && !data) return <p className="text-sm text-slate-400">Loading…</p>;
  if (!data) {
    return (
      <div className="py-20 text-center text-xs text-slate-400 font-medium">
        <div className="inline-block w-6 h-6 border-2 border-[#1d72f2] border-t-transparent rounded-full animate-spin mb-2" />
        <p>Loading your sales dashboard...</p>
      </div>
    );
  }

  const c = data.cards || {
    pending_approvals: 0,
    open_quotations: 0,
    at_risk_deals: 0,
    awaiting_fulfillment: 0,
    unpaid_invoices: 0,
  };
  const firstName = data.full_name ? data.full_name.split(" ")[0] : "Team";
  const atRisk = data.at_risk || [];
  const recentActivity = data.recent_activity || [];

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Welcome back, ${firstName}`}
        subtitle={
          "Operational overview: pipeline movement, pending approvals, and deal risks." +
          (lastUpdated ? ` · live, updated ${lastUpdated.toLocaleTimeString()}` : "")
        }
        actions={
          <div className="flex items-center gap-2.5">
            <Link
              to="/build"
              className="bg-[#1d72f2] hover:bg-[#155fc7] text-white rounded-lg px-3.5 py-1.5 text-xs font-semibold shadow-2xs transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              <span>+</span> New Quotation
            </Link>
            {can("view_approvals") && (
              <Link
                to="/approvals"
                className="bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 rounded-lg px-3.5 py-1.5 text-xs font-semibold shadow-2xs transition-colors"
              >
                View Approvals
              </Link>
            )}
          </div>
        }
      />

      {/* Operational KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3.5">
        <StatCard
          label="Pending Approvals"
          value={c.pending_approvals}
          tone={c.pending_approvals ? "amber" : "slate"}
          hint="Awaiting manager/finance decision"
        />
        <StatCard
          label="Open Quotations"
          value={c.open_quotations}
          hint="Active commercial negotiations"
        />
        <StatCard
          label="At-Risk Deals"
          value={c.at_risk_deals}
          tone={c.at_risk_deals ? "red" : "slate"}
          hint="Flagged by Sentinel models"
        />
        <StatCard
          label="Awaiting Fulfillment"
          value={c.awaiting_fulfillment}
          tone={c.awaiting_fulfillment ? "indigo" : "slate"}
          hint="Confirmed, pending shipment"
        />
        <StatCard
          label="Unpaid Invoices"
          value={c.unpaid_invoices}
          tone={c.unpaid_invoices ? "amber" : "slate"}
          hint="Outstanding receivables"
        />
      </div>

      {/* Activity & Attention Panels */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <section className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs">
          <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-100">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
              Requires Attention
            </h3>
            <span className="text-[11px] font-semibold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-md border border-rose-100">
              Sentinel Anomaly Flags
            </span>
          </div>

          {atRisk.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-400 font-medium">
              ✓ No stalled or anomalous deals flagged.
            </div>
          ) : (
            <ul className="space-y-2.5">
              {atRisk.map((r) => (
                <li
                  key={r.quotation_id}
                  className="bg-slate-50/70 border border-slate-200/80 rounded-lg p-3 hover:border-slate-300 transition-colors"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Link
                      to="/health"
                      className="text-xs font-bold text-slate-900 hover:text-[#1d72f2] transition-colors"
                    >
                      #{r.quotation_id} · {r.customer_name}
                    </Link>
                    <StateBadge state={r.state} />
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1">
                    Inactive for <span className="font-semibold text-slate-700">{r.days_inactive}d</span> · {r.reason}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs">
          <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-100">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
              Recent Activity
            </h3>
            <span className="text-[11px] font-semibold text-slate-400">Pipeline Timeline</span>
          </div>

          <ul className="divide-y divide-slate-100">
            {recentActivity.map((a) => (
              <li key={a.quotation_id} className="py-2.5 flex items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-slate-900 truncate">
                    #{a.quotation_id} {a.customer_name}
                  </p>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Assigned: {a.rep_name} · {(a.last_activity_at || "").slice(0, 10)}
                  </p>
                </div>
                <StateBadge state={a.state} />
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
