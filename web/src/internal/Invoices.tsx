import { useEffect, useState } from "react";
import { api, type InvoiceDetailOut, type InvoiceRow } from "@/lib/api";
import {
  EmptyRow, ErrorBanner, FilterTabs, PageHeader, Pagination, StatCard, money,
} from "./components";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "unpaid", label: "Unpaid" },
  { key: "paid", label: "Paid" },
];

/** Screens 12 & 13 — Invoices list, and the detail view a row opens. */
export default function Invoices() {
  const [rows, setRows] = useState<InvoiceRow[]>([]);
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<InvoiceDetailOut | null>(null);
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
    api.getPaginated<InvoiceRow[]>(`/api/invoices?${q.toString()}`)
      .then((res) => {
        setRows(res.data);
        setTotalCount(res.totalCount);
        setTotalPages(res.totalPages);
      })
      .catch((e) => setError(String(e.message)));
  }, [filter, page, pageSize]);

  function open(id: number) {
    setError(null);
    api.get<InvoiceDetailOut>(`/api/invoices/${id}`)
      .then(setSelected)
      .catch((e) => setError(String(e.message)));
  }

  const billed = rows.reduce((n, r) => n + Number(r.total), 0);
  const outstanding = rows.reduce((n, r) => n + Number(r.outstanding), 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Invoices"
        subtitle="Every invoice generated from one-time and recurring orders."
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

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <StatCard label="Total invoices" value={totalCount || rows.length} />
        <StatCard label="Total billed (page)" value={money(billed)} />
        <StatCard label="Outstanding (page)" value={money(outstanding)}
          tone={outstanding > 0 ? "amber" : "emerald"} />
      </div>

      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2 font-medium">Invoice #</th>
              <th className="px-4 py-2 font-medium">Customer</th>
              <th className="px-4 py-2 font-medium">Kind</th>
              <th className="px-4 py-2 font-medium text-right">Amount</th>
              <th className="px-4 py-2 font-medium text-right">Outstanding</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <EmptyRow colSpan={7} text="No invoices match this filter." />}
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="px-4 py-2 font-medium">{r.reference}</td>
                <td className="px-4 py-2">
                  {r.customer_name}
                  <span className="block text-xs text-slate-400">quote #{r.quotation_id}</span>
                </td>
                <td className="px-4 py-2 text-slate-600">
                  {r.kind.replace("_", " ")}
                  {r.period_key && <span className="text-slate-400"> · {r.period_key}</span>}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">{money(r.total)}</td>
                <td className={`px-4 py-2 text-right tabular-nums ${
                  Number(r.outstanding) > 0 ? "text-amber-700 font-medium" : "text-slate-400"}`}>
                  {money(r.outstanding)}
                </td>
                <td className="px-4 py-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    r.status === "paid" ? "bg-emerald-100 text-emerald-800"
                    : "bg-amber-100 text-amber-800"}`}>
                    {r.status}
                  </span>
                </td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => open(r.id)}
                    data-testid={`open-invoice-${r.id}`}
                    className="text-xs text-slate-600 border border-slate-200 rounded px-2 py-1 hover:bg-white">
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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

      {selected && <InvoiceDetail invoice={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

/** Screen 13 — Invoice Detail. */
function InvoiceDetail({
  invoice, onClose,
}: {
  invoice: InvoiceDetailOut;
  onClose: () => void;
}) {
  return (
    <section className="bg-white border border-slate-200 rounded-lg p-5" data-testid="invoice-detail">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-slate-900">
            {invoice.reference} · {invoice.customer_name}
          </h3>
          <p className="text-xs text-slate-500">
            {invoice.kind.replace("_", " ")} · from quote #{invoice.quotation_id}
            {invoice.issued_at && ` · issued ${invoice.issued_at}`}
          </p>
        </div>
        <button onClick={onClose} className="text-sm text-slate-400 hover:text-slate-700">
          Close
        </button>
      </div>

      {/* Order Confirmed -> Shipped -> Invoiced -> Paid */}
      <ol className="flex items-center gap-2 mb-5">
        {invoice.tracker.map((t, i) => (
          <li key={t.step} className="flex items-center gap-2">
            <span className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded ${
              t.done ? "bg-emerald-100 text-emerald-800 font-medium" : "bg-slate-100 text-slate-400"}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${t.done ? "bg-emerald-600" : "bg-slate-300"}`} />
              {t.step}
            </span>
            {i < invoice.tracker.length - 1 && <span className="text-slate-300">→</span>}
          </li>
        ))}
      </ol>

      <table className="w-full text-sm mb-4">
        <thead>
          <tr className="text-left text-slate-500 border-b border-slate-200">
            <th className="py-2 font-medium">Description</th>
            <th className="py-2 font-medium text-right">Qty</th>
            <th className="py-2 font-medium text-right">Unit</th>
            <th className="py-2 font-medium text-right">Amount</th>
          </tr>
        </thead>
        <tbody>
          {invoice.lines.map((ln, i) => (
            <tr key={i} className="border-b border-slate-100">
              <td className="py-2">{ln.description}</td>
              <td className="py-2 text-right">{ln.qty}</td>
              <td className="py-2 text-right tabular-nums">{money(ln.unit_price)}</td>
              <td className="py-2 text-right tabular-nums">{money(ln.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {invoice.credit_notes.map((c, i) => (
        <p key={i} className="text-sm text-amber-700">
          Credit note −{money(c.amount)} · {c.reason}
        </p>
      ))}
      {invoice.payments.map((p, i) => (
        <p key={i} className="text-sm text-emerald-700">
          Payment {money(p.amount)} · {p.method} · {p.paid_at}
        </p>
      ))}

      <div className="flex justify-end gap-6 border-t border-slate-100 mt-4 pt-3 text-sm">
        <span className="text-slate-500">Billed <strong className="text-slate-900">{money(invoice.total)}</strong></span>
        <span className="text-slate-500">Paid <strong className="text-slate-900">{money(invoice.paid)}</strong></span>
        <span className="text-slate-500">
          Outstanding{" "}
          <strong className={Number(invoice.outstanding) > 0 ? "text-amber-700" : "text-emerald-700"}>
            {money(invoice.outstanding)}
          </strong>
        </span>
      </div>
    </section>
  );
}
