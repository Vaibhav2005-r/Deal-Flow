import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type PendingOrder, type StockRow } from "@/lib/api";
import { EmptyRow, ErrorBanner, PageHeader, Pagination, StatCard, StateBadge } from "./components";
import { useAutoRefresh } from "@/lib/live";

/** Screen 7 — Fulfillment and Stock. Live stock per warehouse, plus every
 *  order still waiting to ship. */
export default function FulfillmentList() {
  // re-fetch on an interval and on tab focus, so the view tracks the database
  const tick = useAutoRefresh();
  const [stock, setStock] = useState<StockRow[]>([]);
  const [pending, setPending] = useState<PendingOrder[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [warehouse, setWarehouse] = useState("all");
  const [lowOnly, setLowOnly] = useState(false);
  const [warehouseList, setWarehouseList] = useState<string[]>([]);

  useEffect(() => {
    api.get<Array<{ code: string }>>("/api/warehouses")
      .then((whs) => setWarehouseList(whs.map((w) => w.code)))
      .catch(() => {});
  }, [tick]);

  // Pagination for Pending Orders
  const [pendingPage, setPendingPage] = useState(1);
  const [pendingPageSize, setPendingPageSize] = useState(10);
  const [pendingTotal, setPendingTotal] = useState(0);
  const [pendingTotalPages, setPendingTotalPages] = useState(1);

  // Pagination for Stock by Warehouse
  const [stockPage, setStockPage] = useState(1);
  const [stockPageSize, setStockPageSize] = useState(25);
  const [stockTotal, setStockTotal] = useState(0);
  const [stockTotalPages, setStockTotalPages] = useState(1);

  useEffect(() => {
    api.getPaginated<PendingOrder[]>(`/api/fulfillment/pending?page=${pendingPage}&page_size=${pendingPageSize}`)
      .then((res) => {
        setPending(res.data);
        setPendingTotal(res.totalCount);
        setPendingTotalPages(res.totalPages);
      })
      .catch((e) => setError(String(e.message)));
  }, [pendingPage, pendingPageSize, tick]);

  useEffect(() => {
    const q = new URLSearchParams({
      page: String(stockPage),
      page_size: String(stockPageSize),
      ...(warehouse !== "all" ? { warehouse } : {}),
      ...(lowOnly ? { low_only: "true" } : {}),
    });
    api.getPaginated<StockRow[]>(`/api/fulfillment/stock?${q.toString()}`)
      .then((res) => {
        setStock(res.data);
        setStockTotal(res.totalCount);
        setStockTotalPages(res.totalPages);
      })
      .catch((e) => setError(String(e.message)));
  }, [stockPage, stockPageSize, warehouse, lowOnly, tick]);

  const warehouses = useMemo(
    () => (warehouseList.length > 0
      ? warehouseList
      : Array.from(new Set(stock.map((s) => s.warehouse))).sort()),
    [warehouseList, stock],
  );
  const rows = stock;

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
        <StatCard label="Stock lines" value={stockTotal || stock.length} hint={`${warehouses.length} warehouses`} />
        <StatCard label="Units reserved" value={reserved} tone="indigo"
          hint="allocated, not yet shipped" />
        <StatCard label="Low stock lines" value={lowLines}
          tone={lowLines ? "amber" : "slate"} hint="5 or fewer available on page" />
        <StatCard label="Orders pending" value={pendingTotal || pending.length}
          tone={pendingTotal || pending.length ? "indigo" : "slate"} hint="confirmed, not shipped" />
      </div>

      <section className="bg-white border border-slate-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Orders pending fulfillment</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200 text-xs uppercase tracking-wider">
              <th className="py-2.5 font-semibold">Order</th>
              <th className="py-2.5 font-semibold">Customer</th>
              <th className="py-2.5 font-semibold">State</th>
              <th className="py-2.5 font-semibold">Allocation Status</th>
              <th className="py-2.5 font-semibold">Fulfillment Hubs</th>
              <th className="py-2.5 font-semibold text-right">Net Value</th>
              <th className="py-2.5 font-semibold text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {pending.length === 0 && <EmptyRow colSpan={7} text="Nothing awaiting fulfillment." />}
            {pending.map((o) => (
              <tr key={o.quotation_id} className="border-b border-slate-100 hover:bg-slate-50/60 transition-colors">
                <td className="py-2.5">
                  <Link to={`/pipeline?id=${o.quotation_id}`} className="font-mono font-semibold text-indigo-600 hover:underline">
                    #{o.quotation_id}
                  </Link>
                </td>
                <td className="py-2.5 font-medium text-slate-800">{o.customer_name}</td>
                <td className="py-2.5"><StateBadge state={o.state} /></td>
                <td className="py-2.5">
                  {o.status === "Backorder" ? (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-amber-100 text-amber-900 border border-amber-300">
                      ⚠️ Backorder
                    </span>
                  ) : o.status === "Split" ? (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-purple-100 text-purple-900 border border-purple-300">
                      ⚡ Split ({o.shipment_count} shipments)
                    </span>
                  ) : o.status === "Single site" ? (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-800 border border-blue-200">
                      Single site
                    </span>
                  ) : (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-500">
                      Not planned
                    </span>
                  )}
                </td>
                <td className="py-2.5">
                  {o.warehouses.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {o.warehouses.map((w) => (
                        <span key={w} className="font-mono text-xs bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded text-slate-700">
                          {w}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
                <td className="py-2.5 text-right tabular-nums font-semibold text-slate-800">
                  {new Intl.NumberFormat("en-IN").format(Number(o.net_total))}
                </td>
                <td className="py-2.5 text-right">
                  <Link
                    to={`/pipeline?id=${o.quotation_id}`}
                    className="inline-flex items-center text-xs font-semibold text-indigo-600 hover:text-indigo-800 bg-indigo-50 hover:bg-indigo-100 px-2.5 py-1 rounded transition-colors"
                  >
                    Manage Split →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-3">
          <Pagination
            page={pendingPage}
            pageSize={pendingPageSize}
            totalCount={pendingTotal}
            totalPages={pendingTotalPages}
            onPageChange={setPendingPage}
            onPageSizeChange={(sz) => {
              setPendingPageSize(sz);
              setPendingPage(1);
            }}
            pageSizeOptions={[5, 10, 25, 50]}
          />
        </div>
      </section>

      <section className="bg-white border border-slate-200 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-700">Stock by warehouse</h3>
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-500 flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={lowOnly}
                onChange={(e) => {
                  setLowOnly(e.target.checked);
                  setStockPage(1);
                }}
              />
              low stock only
            </label>
            <select
              value={warehouse}
              onChange={(e) => {
                setWarehouse(e.target.value);
                setStockPage(1);
              }}
              className="border border-slate-300 rounded px-2 py-1 text-xs"
            >
              <option value="all">All warehouses</option>
              {warehouses.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
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
        <div className="mt-3">
          <Pagination
            page={stockPage}
            pageSize={stockPageSize}
            totalCount={stockTotal}
            totalPages={stockTotalPages}
            onPageChange={setStockPage}
            onPageSizeChange={(sz) => {
              setStockPageSize(sz);
              setStockPage(1);
            }}
            pageSizeOptions={[10, 25, 50, 100]}
          />
        </div>
      </section>
    </div>
  );
}
