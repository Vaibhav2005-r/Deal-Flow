import { useEffect, useState } from "react";
import { api, type InvoiceDetailOut, type InvoiceRow, type InvoiceSummary } from "@/lib/api";
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
  { key: "all", label: "All Invoices" },
  { key: "unpaid", label: "Unpaid / Pending" },
  { key: "paid", label: "Paid" },
];

export default function Invoices() {
  // re-fetch on an interval and on tab focus, so the view tracks the database
  const tick = useAutoRefresh();
  const [rows, setRows] = useState<InvoiceRow[]>([]);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [summary, setSummary] = useState<InvoiceSummary | null>(null);
  const [selected, setSelected] = useState<InvoiceDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  // Fetch summary directly from the database matching the active filter and search
  useEffect(() => {
    const q = new URLSearchParams();
    if (filter !== "all") q.set("status", filter);
    if (search.trim()) q.set("search", search.trim());
    api.get<InvoiceSummary>(`/api/invoices/summary${q.toString() ? `?${q.toString()}` : ""}`)
      .then(setSummary)
      .catch(() => {});
  }, [filter, search, tick]);

  // Fetch paginated invoices list from the database
  useEffect(() => {
    setLoading(true);
    const q = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      ...(filter !== "all" ? { status: filter } : {}),
      ...(search.trim() ? { search: search.trim() } : {}),
    });
    api.getPaginated<InvoiceRow[]>(`/api/invoices?${q.toString()}`)
      .then((res) => {
        setRows(res.data);
        setTotalCount(res.totalCount);
        setTotalPages(res.totalPages);
      })
      .catch((e) => setError(String(e.message)))
      .finally(() => setLoading(false));
  }, [filter, search, page, pageSize, tick]);

  function open(id: number) {
    setError(null);
    api.get<InvoiceDetailOut>(`/api/invoices/${id}`)
      .then(setSelected)
      .catch((e) => setError(String(e.message)));
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Invoices & Billing"
        subtitle="Manage recognized customer billing, payment schedules, and outstanding balances."
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative">
              <input
                type="search"
                placeholder="Search reference or customer..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="bg-white border border-slate-200 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-[#1d72f2] w-64 shadow-2xs"
              />
              <svg
                className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5 pointer-events-none"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <FilterTabs
              options={FILTERS}
              value={filter}
              onChange={(f) => {
                setFilter(f);
                setPage(1);
              }}
            />
          </div>
        }
      />

      <ErrorBanner error={error} />

      {/* Financial Summary KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Total Invoices"
          value={summary?.total_invoices ?? totalCount}
          hint={filter !== "all" ? `${filter} filter` : "in database"}
        />
        <StatCard
          label="Total Billed"
          value={`$${money(summary?.total_billed ?? "0")}`}
          hint="Gross ledger billed"
        />
        <StatCard
          label="Total Paid"
          value={`$${money(summary?.total_paid ?? "0")}`}
          tone="emerald"
          hint={`${summary?.paid_invoices ?? 0} invoices settled`}
        />
        <StatCard
          label="Total Outstanding"
          value={`$${money(summary?.total_outstanding ?? "0")}`}
          tone={Number(summary?.total_outstanding ?? 0) > 0 ? "amber" : "emerald"}
          hint={`${summary?.unpaid_invoices ?? 0} invoices pending`}
        />
      </div>

      {/* Main Invoices Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50/80 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
              <tr>
                <th className="px-4 py-3">Invoice Ref</th>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3">Billing Type</th>
                <th className="px-4 py-3 text-right">Total Amount</th>
                <th className="px-4 py-3 text-right">Outstanding</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-sans">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-slate-400">
                    <div className="flex items-center justify-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[#1d72f2] animate-ping" />
                      <span>Loading invoices from database...</span>
                    </div>
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <EmptyRow colSpan={7} text="No invoices match this filter." />
              ) : (
                rows.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-4 py-3 font-bold text-slate-900">
                      <span className="text-[#1d72f2]">{r.reference}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-semibold text-slate-900 block">{r.customer_name}</span>
                      <span className="text-[11px] text-slate-400">Quote #{r.quotation_id}</span>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      <span className="capitalize">{r.kind.replace("_", " ")}</span>
                      {r.period_key && <span className="text-slate-400"> · {r.period_key}</span>}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-bold text-slate-900">
                      ${money(r.total)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right tabular-nums font-semibold ${
                        Number(r.outstanding) > 0 ? "text-amber-700" : "text-slate-400"
                      }`}
                    >
                      ${money(r.outstanding)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                          r.status === "paid"
                            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                            : "bg-amber-50 text-amber-700 border-amber-200"
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            r.status === "paid" ? "bg-emerald-500" : "bg-amber-500"
                          }`}
                        />
                        <span className="capitalize">{r.status}</span>
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => open(r.id)}
                        data-testid={`open-invoice-${r.id}`}
                        className="text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-md px-3 py-1 transition-colors shadow-2xs cursor-pointer"
                      >
                        Inspect
                      </button>
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
        pageSizeOptions={[10, 20, 50, 100]}
      />

      {/* Invoice Detail Drawer */}
      {selected && <InvoiceDetail invoice={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function InvoiceDetail({
  invoice,
  onClose,
}: {
  invoice: InvoiceDetailOut;
  onClose: () => void;
}) {
  return (
    <section
      className="bg-white border border-slate-200/90 rounded-xl p-6 shadow-md space-y-5"
      data-testid="invoice-detail"
    >
      <div className="flex items-start justify-between pb-3 border-b border-slate-100">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-lg font-bold text-slate-900">
              {invoice.reference} — {invoice.customer_name}
            </h2>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700 uppercase">
              {invoice.kind.replace("_", " ")}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Generated from Quotation #{invoice.quotation_id}
            {invoice.issued_at && ` · Issued on ${invoice.issued_at}`}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-xs font-semibold text-slate-500 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-md px-3 py-1 transition-colors cursor-pointer"
        >
          Close Detail
        </button>
      </div>

      {/* Order -> Shipped -> Invoiced -> Paid Milestone Tracker */}
      <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-4">
        <p className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
          Order Lifecycle Status
        </p>
        <ol className="flex flex-wrap items-center gap-3">
          {invoice.tracker.map((t, i) => (
            <li key={t.step} className="flex items-center gap-2.5">
              <span
                className={`inline-flex items-center gap-1.5 text-xs px-3 py-1 rounded-full font-semibold border ${
                  t.done
                    ? "bg-emerald-50 text-emerald-700 border-emerald-200 shadow-2xs"
                    : "bg-white text-slate-400 border-slate-200"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${t.done ? "bg-emerald-500" : "bg-slate-300"}`}
                />
                {t.step}
              </span>
              {i < invoice.tracker.length - 1 && (
                <span className="text-slate-300 font-bold">→</span>
              )}
            </li>
          ))}
        </ol>
      </div>

      {/* Invoice Line Breakdown */}
      <div>
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
          Line Item Breakdown
        </h3>
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50/80 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
              <tr>
                <th className="py-2.5 px-3">Description</th>
                <th className="py-2.5 px-3 text-right">Quantity</th>
                <th className="py-2.5 px-3 text-right">Unit Price</th>
                <th className="py-2.5 px-3 text-right">Total Net</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {invoice.lines.map((ln, i) => (
                <tr key={i} className="hover:bg-slate-50/70">
                  <td className="py-2.5 px-3 font-semibold text-slate-800">{ln.description}</td>
                  <td className="py-2.5 px-3 text-right font-medium text-slate-700">{ln.qty}</td>
                  <td className="py-2.5 px-3 text-right tabular-nums text-slate-600">
                    ${money(ln.unit_price)}
                  </td>
                  <td className="py-2.5 px-3 text-right tabular-nums font-bold text-slate-900">
                    ${money(ln.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Credit notes & payment logs if present */}
      {invoice.credit_notes.length > 0 && (
        <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 space-y-1">
          {invoice.credit_notes.map((c, i) => (
            <p key={i} className="font-medium">
              Credit Note: −${money(c.amount)} · Reason: {c.reason}
            </p>
          ))}
        </div>
      )}

      {invoice.payments.length > 0 && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 space-y-1">
          {invoice.payments.map((p, i) => (
            <p key={i} className="font-medium">
              Payment Confirmed: ${money(p.amount)} via {p.method} ({p.paid_at})
            </p>
          ))}
        </div>
      )}

      {/* Summary Footer */}
      <div className="flex flex-wrap items-center justify-end gap-6 border-t border-slate-100 pt-4 text-xs">
        <span className="text-slate-500">
          Total Billed: <strong className="text-slate-900 font-bold ml-1">${money(invoice.total)}</strong>
        </span>
        <span className="text-slate-500">
          Total Paid: <strong className="text-slate-900 font-bold ml-1">${money(invoice.paid)}</strong>
        </span>
        <span className="text-slate-500">
          Balance Outstanding:{" "}
          <strong
            className={`font-bold ml-1 ${
              Number(invoice.outstanding) > 0 ? "text-amber-700" : "text-emerald-700"
            }`}
          >
            ${money(invoice.outstanding)}
          </strong>
        </span>
      </div>
    </section>
  );
}
