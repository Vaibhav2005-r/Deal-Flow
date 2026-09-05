import { useEffect, useState } from "react";
import { api, type SubscriptionRow } from "@/lib/api";
import {
  EmptyRow, ErrorBanner, FilterTabs, PageHeader, StatCard, money,
} from "./components";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "paused", label: "Paused" },
  { key: "cancelled", label: "Cancelled" },
];

const TONE: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-800",
  paused: "bg-amber-100 text-amber-800",
  cancelled: "bg-slate-100 text-slate-600",
};

/** Screen 9 — Subscriptions. Every recurring plan across every customer,
 *  regardless of which order it came from. */
export default function Subscriptions() {
  const [rows, setRows] = useState<SubscriptionRow[]>([]);
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const q = filter === "all" ? "" : `?status=${filter}`;
    api.get<SubscriptionRow[]>(`/api/subscriptions${q}`)
      .then(setRows)
      .catch((e) => setError(String(e.message)));
  }, [filter]);

  const mrr = rows
    .filter((r) => r.status === "active")
    .reduce((n, r) => n + Number(r.amount), 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Subscriptions"
        subtitle="Every recurring plan across every customer, regardless of which order it came from."
        actions={<FilterTabs options={FILTERS} value={filter} onChange={setFilter} />}
      />
      <ErrorBanner error={error} />

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <StatCard label="Subscriptions shown" value={rows.length} />
        <StatCard label="Active recurring value" value={money(mrr)} tone="emerald"
          hint="per billing cycle" />
        <StatCard label="Next bill" value={rows[0]?.next_bill_date ?? "—"}
          hint={rows[0]?.customer_name ?? "nothing scheduled"} />
      </div>

      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2 font-medium">Customer</th>
              <th className="px-4 py-2 font-medium">Plan</th>
              <th className="px-4 py-2 font-medium">Cycle</th>
              <th className="px-4 py-2 font-medium">Started</th>
              <th className="px-4 py-2 font-medium">Next bill</th>
              <th className="px-4 py-2 font-medium text-right">Amount</th>
              <th className="px-4 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <EmptyRow colSpan={7} text="No subscriptions match this filter." />}
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-slate-100">
                <td className="px-4 py-2">
                  {r.customer_name}
                  <span className="block text-xs text-slate-400 uppercase">{r.customer_tier}</span>
                </td>
                <td className="px-4 py-2">
                  {r.plan}
                  <span className="block text-xs text-slate-400">from quote #{r.quotation_id}</span>
                </td>
                <td className="px-4 py-2 text-slate-600">{r.cycle}</td>
                <td className="px-4 py-2 text-slate-500 tabular-nums">{r.start_date}</td>
                <td className="px-4 py-2 tabular-nums font-medium">{r.next_bill_date}</td>
                <td className="px-4 py-2 text-right tabular-nums">{money(r.amount)}</td>
                <td className="px-4 py-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${TONE[r.status] ?? ""}`}>
                    {r.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
