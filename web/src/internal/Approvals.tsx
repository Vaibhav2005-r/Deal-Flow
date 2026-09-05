import { useCallback, useEffect, useState } from "react";
import { api, type Quote } from "@/lib/api";
import { ApprovalTrail, LineTable, RiskBadge, StateBadge } from "./components";

export default function Approvals() {
  const [queue, setQueue] = useState<Quote[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

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

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-slate-900">Approval queue</h2>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-sm rounded px-3 py-2">
          {error}
        </div>
      )}

      {!queue.length && (
        <p className="text-sm text-slate-500" data-testid="empty-queue">
          Nothing waiting on you.
        </p>
      )}

      {queue.map((q) => (
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
