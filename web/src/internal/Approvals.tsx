import { useCallback, useEffect, useState } from "react";
import { api, type Quote } from "@/lib/api";
import {
  ApprovalTrail, EmptyRow, FilterTabs, LineTable, PageHeader, RiskBadge,
  StateBadge, money,
} from "./components";

const FILTERS = [
  { key: "pending", label: "Pending" },
  { key: "returned", label: "Returned" },
  { key: "approved", label: "Approved" },
];

const BAND_TONE: Record<string, string> = {
  HIGH: "bg-red-100 text-red-800",
  MEDIUM: "bg-amber-100 text-amber-800",
  LOW: "bg-emerald-100 text-emerald-800",
};

export default function Approvals() {
  const [queue, setQueue] = useState<Quote[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [filter, setFilter] = useState("pending");
  const [open, setOpen] = useState<number | null>(null);

  const load = useCallback(() => {
    api.get<Quote[]>("/api/approvals")
      .then(setQueue)
      .catch((e) => setError(String(e.message)));
  }, []);

  useEffect(load, [load]);

  async function decide(id: number, action: "approve" | "reject" | "return") {
    setError(null);
    let reason: string | null = null;
    if (action !== "approve") {
      reason = window.prompt(`Reason for ${action}?`);
      if (!reason?.trim()) return;   // §7: reason is required
    }
    setBusy(id);
    try {
      await api.post(`/api/quotes/${id}/${action}`, reason ? { reason } : {});
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  /** Pending is the live queue; the other two are history, read off the
   *  trail rather than a second endpoint. */
  const rows = queue.filter((q) => {
    if (filter === "pending") return q.current_stage !== null;
    const decisions = q.approval_steps.map((s) => s.decision);
    if (filter === "returned") {
      return decisions.includes("RETURNED") || decisions.includes("REJECTED");
    }
    return decisions.includes("APPROVED");
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Approvals"
        subtitle="Every quotation that needed, needs, or went through discount approval."
        actions={<FilterTabs options={FILTERS} value={filter} onChange={setFilter} />}
      />

      {/* The queue is a table first: a manager triages by risk and stage, then
          opens one quote to see why it was flagged. */}
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2 font-medium">Quotation</th>
              <th className="px-4 py-2 font-medium">Customer</th>
              <th className="px-4 py-2 font-medium">Blended risk</th>
              <th className="px-4 py-2 font-medium">Stage</th>
              <th className="px-4 py-2 font-medium text-right">Net</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <EmptyRow colSpan={6} text="Nothing in this view." />
            )}
            {rows.map((q) => (
              <tr key={q.id} className="border-t border-slate-100">
                <td className="px-4 py-2 font-medium">#Q-{q.id}</td>
                <td className="px-4 py-2">
                  {q.customer_name}
                  <span className="block text-xs text-slate-400 uppercase">
                    {q.customer_tier}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                    BAND_TONE[q.risk_band ?? ""] ?? "bg-slate-100 text-slate-600"}`}>
                    {q.risk_band ?? "—"}
                    {q.risk_score && ` ${Number(q.risk_score).toFixed(1)}`}
                  </span>
                </td>
                <td className="px-4 py-2 text-slate-600">
                  {q.current_stage?.replaceAll("_", " ") ?? (
                    <span className="text-slate-300">complete</span>
                  )}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {money(q.totals.net_total as string)}
                </td>
                <td className="px-4 py-2 text-right">
                  <button
                    onClick={() => setOpen(open === q.id ? null : q.id)}
                    data-testid={`inspect-${q.id}`}
                    className="text-xs text-slate-600 border border-slate-200 rounded px-2 py-1"
                  >
                    {open === q.id ? "Hide" : "Why flagged?"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-sm rounded px-3 py-2">
          {error}
        </div>
      )}

      {rows.filter((q) => open === q.id).map((q) => (
        <section key={q.id} className="bg-white border border-slate-200 rounded-lg p-4" data-testid={`quote-${q.id}`}>
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="font-semibold text-slate-900">
                Quote #{q.id} · {q.customer_name}
              </h3>
              <p className="text-xs text-slate-500">
                {q.customer_tier} tier · {q.totals.line_count} lines · net{" "}
                {new Intl.NumberFormat("en-IN").format(Number(q.totals.net_total))}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <StateBadge state={q.state} />
              <RiskBadge score={q.risk_score ? Number(q.risk_score) : null} />
            </div>
          </div>

          <LineTable lines={q.lines} />

          <div className="mt-3 pt-3 border-t border-slate-100">
            <ApprovalTrail steps={q.approval_steps} />
          </div>

          <div className="flex gap-2 mt-4">
            <button
              onClick={() => decide(q.id, "approve")}
              disabled={busy === q.id}
              data-testid={`approve-${q.id}`}
              className="bg-emerald-700 text-white rounded px-4 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Approve
            </button>
            <button
              onClick={() => decide(q.id, "return")}
              disabled={busy === q.id}
              className="bg-amber-600 text-white rounded px-4 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Return for revision
            </button>
            <button
              onClick={() => decide(q.id, "reject")}
              disabled={busy === q.id}
              className="bg-red-700 text-white rounded px-4 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Reject
            </button>
          </div>
        </section>
      ))}
    </div>
  );
}
