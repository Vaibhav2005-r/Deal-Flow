import { useEffect, useState } from "react";
import { api, type SubscriptionRow } from "@/lib/api";
import {
  EmptyRow,
  ErrorBanner,
  FilterTabs,
  PageHeader,
  Pagination,
  StatCard,
  money,
} from "./components";
import { useAutoRefresh } from "@/lib/live";

const FILTERS = [
  { key: "all", label: "All Plans" },
  { key: "active", label: "Active" },
  { key: "paused", label: "Paused" },
  { key: "cancelled", label: "Cancelled" },
];

export default function Subscriptions() {
  // re-fetch on an interval and on tab focus, so the view tracks the database
  const tick = useAutoRefresh();
  const [rows, setRows] = useState<SubscriptionRow[]>([]);
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    const q = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      ...(filter !== "all" ? { status: filter } : {}),
    });
    api.getPaginated<SubscriptionRow[]>(`/api/subscriptions?${q.toString()}`)
      .then((res) => {
        setRows(res.data);
        setTotalCount(res.totalCount);
        setTotalPages(res.totalPages);
      })
      .catch((e) => setError(String(e.message)));
  }, [filter, page, pageSize, tick]);

  const mrr = rows
    .filter((r) => r.status === "active")
    .reduce((n, r) => n + Number(r.amount), 0);

  const getStatusBadge = (status: string) => {
    switch (status?.toLowerCase()) {
      case "active":
        return "bg-emerald-50 text-emerald-700 border-emerald-200";
      case "paused":
        return "bg-amber-50 text-amber-700 border-amber-200";
      case "cancelled":
        return "bg-slate-100 text-slate-600 border-slate-200";
      default:
        return "bg-slate-50 text-slate-700 border-slate-200";
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Recurring Subscriptions"
        subtitle="Manage recurring SaaS plans, billing schedules, and customer renewal cycles across all accounts."
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

      {/* Subscription KPI Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="Total Subscriptions"
          value={totalCount || rows.length}
          hint={filter !== "all" ? `${filter} filter` : "in database"}
        />
        <StatCard
          label="Active Recurring MRR"
          value={`$${money(mrr)}`}
          tone="emerald"
          hint="Per active billing cycle"
        />
        <StatCard
          label="Next Scheduled Bill"
          value={rows[0]?.next_bill_date ?? "—"}
          hint={rows[0]?.customer_name ?? "No pending schedule"}
        />
      </div>

      {/* Subscriptions Grid Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50/80 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
              <tr>
                <th className="px-4 py-3">Customer & Tier</th>
                <th className="px-4 py-3">Plan / Product</th>
                <th className="px-4 py-3">Billing Cycle</th>
                <th className="px-4 py-3">Start Date</th>
                <th className="px-4 py-3">Next Bill Date</th>
                <th className="px-4 py-3 text-right">Recurring Amount</th>
                <th className="px-4 py-3 text-right">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-sans">
              {rows.length === 0 ? (
                <EmptyRow colSpan={7} text="No subscriptions match this filter." />
              ) : (
                rows.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-4 py-3">
                      <span className="font-semibold text-slate-900 block">{r.customer_name}</span>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                        {r.customer_tier} Tier
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-semibold text-slate-800 block">{r.plan}</span>
                      <span className="text-[11px] text-slate-400">Quote #{r.quotation_id}</span>
                    </td>
                    <td className="px-4 py-3 text-slate-600 capitalize font-medium">{r.cycle}</td>
                    <td className="px-4 py-3 text-slate-500 tabular-nums">{r.start_date}</td>
                    <td className="px-4 py-3 tabular-nums font-semibold text-slate-800">
                      {r.next_bill_date}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-bold text-slate-900">
                      ${money(r.amount)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${getStatusBadge(
                          r.status
                        )}`}
                      >
                        <span className="capitalize">{r.status}</span>
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

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
