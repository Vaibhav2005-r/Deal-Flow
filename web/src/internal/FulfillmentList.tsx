import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type PendingOrder, type StockRow } from "@/lib/api";
import { EmptyRow, ErrorBanner, PageHeader, StatCard, StateBadge } from "./components";

/** Screen 7 — Fulfillment and Stock. Live stock per warehouse, plus every
 *  order still waiting to ship. */
export default function FulfillmentList() {
  const [stock, setStock] = useState<StockRow[]>([]);
  const [pending, setPending] = useState<PendingOrder[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [warehouse, setWarehouse] = useState("all");
  const [lowOnly, setLowOnly] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get<StockRow[]>("/api/fulfillment/stock"),
      api.get<PendingOrder[]>("/api/fulfillment/pending"),
    ]).then(([s, p]) => { setStock(s); setPending(p); })
      .catch((e) => setError(String(e.message)));
  }, []);

  const warehouses = useMemo(
    () => Array.from(new Set(stock.map((s) => s.warehouse))).sort(),
    [stock],
  );
  const rows = useMemo(
    () => stock
      .filter((s) => warehouse === "all" || s.warehouse === warehouse)
      .filter((s) => !lowOnly || s.qty_available <= 5),
    [stock, warehouse, lowOnly],
  );

  const reserved = stock.reduce((n, s) => n + s.qty_reserved, 0);
  const lowLines = stock.filter((s) => s.qty_available <= 5).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Fulfillment & stock"
        subtitle="Live stock per warehouse, and every order still waiting to ship."
      />
      <ErrorBanner error={error} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Stock lines" value={stock.length} hint={`${warehouses.length} warehouses`} />
        <StatCard label="Units reserved" value={reserved} tone="indigo"
          hint="allocated, not yet shipped" />
        <StatCard label="Low stock lines" value={lowLines}
          tone={lowLines ? "amber" : "slate"} hint="5 or fewer available" />
        <StatCard label="Orders pending" value={pending.length}
          tone={pending.length ? "indigo" : "slate"} hint="confirmed, not shipped" />
      </div>

      <section className="bg-white border border-slate-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Orders pending fulfillment</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-2 font-medium">Order</th>
              <th className="py-2 font-medium">Customer</th>
              <th className="py-2 font-medium">State</th>
              <th className="py-2 font-medium">Plan</th>
              <th className="py-2 font-medium">Warehouses</th>
              <th className="py-2 font-medium text-right">Net</th>
            </tr>
          </thead>
          <tbody>
            {pending.length === 0 && <EmptyRow colSpan={6} text="Nothing awaiting fulfillment." />}
            {pending.map((o) => (
              <tr key={o.quotation_id} className="border-b border-slate-100">
                <td className="py-2">
                  <Link to="/pipeline" className="text-slate-900 hover:underline">
                    #{o.quotation_id}
                  </Link>
                </td>
                <td className="py-2">{o.customer_name}</td>
                <td className="py-2"><StateBadge state={o.state} /></td>
                <td className="py-2">
                  <span className={
                    o.status === "Backorder" ? "text-amber-700 font-medium"
                    : o.status === "Not planned" ? "text-slate-400" : "text-slate-700"
                  }>
                    {o.status}
                  </span>
                </td>
                <td className="py-2 text-slate-500">{o.warehouses.join(" + ") || "—"}</td>
                <td className="py-2 text-right tabular-nums">
                  {new Intl.NumberFormat("en-IN").format(Number(o.net_total))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="bg-white border border-slate-200 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-700">Stock by warehouse</h3>
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-500 flex items-center gap-1.5">
              <input type="checkbox" checked={lowOnly}
                onChange={(e) => setLowOnly(e.target.checked)} />
              low stock only
            </label>
            <select value={warehouse} onChange={(e) => setWarehouse(e.target.value)}
              className="border border-slate-300 rounded px-2 py-1 text-xs">
              <option value="all">All warehouses</option>
              {warehouses.map((w) => <option key={w} value={w}>{w}</option>)}
            </select>
          </div>
        </div>
        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white">
              <tr className="text-left text-slate-500 border-b border-slate-200">
                <th className="py-2 font-medium">Warehouse</th>
                <th className="py-2 font-medium">Product</th>
                <th className="py-2 font-medium text-right">On hand</th>
                <th className="py-2 font-medium text-right">Reserved</th>
                <th className="py-2 font-medium text-right">Available</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && <EmptyRow colSpan={5} text="No stock lines match." />}
              {rows.map((s, i) => (
                <tr key={i} className={`border-b border-slate-100 ${s.qty_available <= 0 ? "bg-red-50" : ""}`}>
                  <td className="py-1.5 font-medium text-slate-700">{s.warehouse}</td>
                  <td className="py-1.5">
                    {s.product_name}
                    <span className="block text-xs text-slate-400">{s.sku}</span>
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{s.qty_on_hand}</td>
                  <td className="py-1.5 text-right tabular-nums text-indigo-700">{s.qty_reserved}</td>
                  <td className={`py-1.5 text-right tabular-nums font-medium ${
                    s.qty_available <= 0 ? "text-red-700"
                    : s.qty_available <= 5 ? "text-amber-700" : "text-slate-900"}`}>
                    {s.qty_available}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
