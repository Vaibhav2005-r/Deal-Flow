import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type DashboardOut } from "@/lib/api";
import { ErrorBanner, PageHeader, StatCard, StateBadge } from "./components";

/** Screen 2 — Sales Dashboard / Home. The landing view. */
export default function Dashboard() {
  const [data, setData] = useState<DashboardOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<DashboardOut>("/api/dashboard")
      .then(setData)
      .catch((e) => setError(String(e.message)));
  }, []);

  if (error) return <ErrorBanner error={error} />;
  if (!data) return <p className="text-sm text-slate-400">Loading…</p>;

  const c = data.cards;

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Good to see you, ${data.full_name.split(" ")[0]}`}
        subtitle="What needs attention, and what just moved."
        actions={
          <>
            <Link to="/build" className="bg-slate-900 text-white rounded px-3 py-1.5 text-sm font-medium">
              + New quotation
            </Link>
            <Link to="/approvals" className="border border-slate-300 rounded px-3 py-1.5 text-sm">
              View approvals
            </Link>
          </>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard label="Pending approvals" value={c.pending_approvals}
          tone={c.pending_approvals ? "amber" : "slate"} hint="waiting on a decision" />
        <StatCard label="Open quotations" value={c.open_quotations} hint="live deals" />
        <StatCard label="At-risk deals" value={c.at_risk_deals}
          tone={c.at_risk_deals ? "red" : "slate"} hint="flagged by Sentinel" />
        <StatCard label="Awaiting fulfillment" value={c.awaiting_fulfillment}
          tone={c.awaiting_fulfillment ? "indigo" : "slate"} hint="confirmed, not shipped" />
        <StatCard label="Unpaid invoices" value={c.unpaid_invoices}
          tone={c.unpaid_invoices ? "amber" : "slate"} hint="outstanding" />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <section className="bg-white border border-slate-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Needs attention</h3>
          {data.at_risk.length === 0 ? (
            <p className="text-sm text-slate-400">Nothing flagged. All live deals are moving.</p>
          ) : (
            <ul className="space-y-2">
              {data.at_risk.map((r) => (
                <li key={r.quotation_id} className="border border-slate-100 rounded px-3 py-2">
                  <div className="flex items-center justify-between">
                    <Link to="/health" className="text-sm font-medium text-slate-900 hover:underline">
                      #{r.quotation_id} · {r.customer_name}
                    </Link>
                    <StateBadge state={r.state} />
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    idle {r.days_inactive}d · {r.reason}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="bg-white border border-slate-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Recent activity</h3>
          <ul className="space-y-1.5">
            {data.recent_activity.map((a) => (
              <li key={a.quotation_id} className="text-sm flex items-center gap-2">
                <span className="text-slate-400 tabular-nums text-xs w-20 shrink-0">
                  {a.last_activity_at.slice(0, 10)}
                </span>
                <span className="flex-1 truncate">
                  #{a.quotation_id} {a.customer_name}
                  <span className="text-slate-400"> · {a.rep_name}</span>
                </span>
                <StateBadge state={a.state} />
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
