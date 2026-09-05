import { useCallback, useEffect, useState } from "react";
import { api, type Quote } from "@/lib/api";
import {
  ApprovalTrail,
  EmptyRow,
  ErrorBanner,
  FilterTabs,
  LineTable,
  PageHeader,
  Pagination,
  RiskBadge,
  StateBadge,
  currency,
} from "./components";
import { useAutoRefresh } from "@/lib/live";

const FILTERS = [
  { key: "pending", label: "Pending Approval" },
  { key: "returned", label: "Returned for Revision" },
  { key: "approved", label: "Approved Quotes" },
];

export default function Approvals() {
  // re-fetch on an interval and on tab focus, so the view tracks the database
  const tick = useAutoRefresh();
  const [queue, setQueue] = useState<Quote[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [filter, setFilter] = useState("pending");
  const [open, setOpen] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  const load = useCallback(() => {
    api.getPaginated<Quote[]>(`/api/approvals?page=${page}&page_size=${pageSize}&status=${filter}`)
      .then((res) => {
        setQueue(res.data);
        setTotalCount(res.totalCount);
        setTotalPages(res.totalPages);
      })
      .catch((e) => setError(String(e.message)));
  }, [filter, page, pageSize]);

  useEffect(load, [load, tick]);

  async function decide(id: number, action: "approve" | "reject" | "return") {
    setError(null);
    let reason: string | null = null;
    if (action !== "approve") {
      reason = window.prompt(`Provide justification for ${action === "return" ? "revision request" : "rejection"}:`);
      if (!reason?.trim()) return; // Required reason
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
      <PageHeader
        title="Discount Approvals"
        subtitle="Review, audit, and triage quotation discount requests with rule-based governance and audit trails."
        actions={
          <FilterTabs
            options={FILTERS}
            value={filter}
            onChange={(f) => {
              setFilter(f);
              setPage(1);
            }}
          />
        }
      />

      <ErrorBanner error={error} />

      {/* Main Approvals Data Grid */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50/80 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
              <tr>
                <th className="px-4 py-3">Quotation ID</th>
                <th className="px-4 py-3">Customer & Tier</th>
                <th className="px-4 py-3">Risk Assessment</th>
                <th className="px-4 py-3">Review Stage</th>
                <th className="px-4 py-3 text-right">Net Value</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-sans">
              {queue.length === 0 ? (
                <EmptyRow colSpan={6} text="No approval records matching this stage." />
              ) : (
                queue.map((q) => (
                  <tr
                    key={q.id}
                    className={`hover:bg-slate-50/70 transition-colors ${
                      open === q.id ? "bg-slate-50/50" : ""
                    }`}
                  >
                    <td className="px-4 py-3 font-bold text-slate-900">
                      <span className="text-[#1d72f2]">#Q-{q.id}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-semibold text-slate-900 block">{q.customer_name}</span>
                      <span className="inline-block text-[10px] font-bold text-slate-400 uppercase tracking-wider mt-0.5">
                        {q.customer_tier} Tier
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <RiskBadge score={q.risk_score ? Number(q.risk_score) : null} />
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                        {q.current_stage?.replaceAll("_", " ") ?? "Complete"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-bold text-slate-900">
                      {currency(q.totals?.net_total as string)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setOpen(open === q.id ? null : q.id)}
                        data-testid={`inspect-${q.id}`}
                        className={`text-xs font-semibold px-3 py-1 rounded-md border transition-all cursor-pointer ${
                          open === q.id
                            ? "bg-slate-900 text-white border-slate-900 shadow-2xs"
                            : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                        }`}
                      >
                        {open === q.id ? "Close Details" : "Review Breakdown"}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Expandable Triage Card */}
      {queue
        .filter((q) => open === q.id)
        .map((q) => (
          <div
            key={q.id}
            className="bg-white border border-slate-200/90 rounded-xl p-5 shadow-sm space-y-4"
            data-testid={`quote-${q.id}`}
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-slate-900">
                    Quote #{q.id} — {q.customer_name}
                  </h2>
                  <span className="text-[11px] font-semibold text-slate-400">
                    ({q.customer_tier} Tier)
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  {q.totals?.line_count} line items · Net Total: {currency(q.totals?.net_total as string)}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <StateBadge state={q.state} />
                <RiskBadge score={q.risk_score ? Number(q.risk_score) : null} />
              </div>
            </div>

            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                Line Items & Discount Ceiling Checks
              </h3>
              <LineTable lines={q.lines} />
            </div>

            <div className="pt-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                Approval Lifecycle Audit Trail
              </h3>
              <ApprovalTrail steps={q.approval_steps} />
            </div>

            <div className="flex flex-wrap items-center gap-2.5 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => decide(q.id, "approve")}
                disabled={busy === q.id}
                data-testid={`approve-${q.id}`}
                className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg px-4 py-2 text-xs font-semibold transition-colors disabled:opacity-50 shadow-2xs cursor-pointer flex items-center gap-1.5"
              >
                <span>✓</span> Approve Quotation
              </button>

              <button
                type="button"
                onClick={() => decide(q.id, "return")}
                disabled={busy === q.id}
                data-testid={`return-${q.id}`}
                className="bg-amber-600 hover:bg-amber-700 text-white rounded-lg px-4 py-2 text-xs font-semibold transition-colors disabled:opacity-50 shadow-2xs cursor-pointer flex items-center gap-1.5"
              >
                <span>↩</span> Return for Revision
              </button>

              <button
                type="button"
                onClick={() => decide(q.id, "reject")}
                disabled={busy === q.id}
                data-testid={`reject-${q.id}`}
                className="bg-rose-600 hover:bg-rose-700 text-white rounded-lg px-4 py-2 text-xs font-semibold transition-colors disabled:opacity-50 shadow-2xs cursor-pointer flex items-center gap-1.5"
              >
                <span>✕</span> Reject Quotation
              </button>
            </div>
          </div>
        ))}

      <Pagination
        page={page}
        pageSize={pageSize}
        totalCount={totalCount}
        totalPages={totalPages}
        onPageChange={setPage}
        onPageSizeChange={(sz) => {
          setPageSize(sz);
          setPage(1);
        }}
      />
    </div>
  );
}
