import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type DealHealthAssessment } from "@/lib/api";
import { Pagination, StateBadge } from "./components";
import { useAutoRefresh } from "@/lib/live";

export default function HealthDashboard() {
  // re-fetch on an interval and on tab focus, so the view tracks the database
  const tick = useAutoRefresh();
  const [deals, setDeals] = useState<DealHealthAssessment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterAlertsOnly, setFilterAlertsOnly] = useState(false);
  const [filterInvoicesOnly, setFilterInvoicesOnly] = useState(false);
  const [selectedDeal, setSelectedDeal] = useState<DealHealthAssessment | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  async function loadHealth() {
    setLoading(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
        ...(filterAlertsOnly ? { alerts_only: "true" } : {}),
        ...(filterInvoicesOnly ? { invoices_only: "true" } : {}),
      });
      const res = await api.getPaginated<DealHealthAssessment[]>(`/api/deal-health?${q.toString()}`);
      setDeals(res.data);
      setTotalCount(res.totalCount);
      setTotalPages(res.totalPages);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load deal health");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadHealth();
  }, [page, pageSize, filterAlertsOnly, filterInvoicesOnly, tick]);

  const totalDeals = totalCount || deals.length;
  const invoicedCount = deals.filter((d) => (d.invoice_count ?? 0) > 0).length;
  const overdueCount = deals.filter((d) => d.payment_overdue || d.invoice_status === "overdue").length;
  const alertCount = deals.filter((d) => d.alert).length;
  const stalledCount = deals.filter((d) => d.stalled).length;
  const anomalyCount = deals.filter((d) => d.discount_anomaly).length;

  const displayedDeals = deals;

  const formatCurrency = (val?: string | number) => {
    const num = Number(val || 0);
    return `₹${num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Deal Health &amp; Sentinel Alerts</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Real-time statistical anomaly monitoring (§5.5) and live invoice telemetry evaluated from MySQL.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setFilterInvoicesOnly(!filterInvoicesOnly);
              setPage(1);
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors border ${
              filterInvoicesOnly
                ? "bg-indigo-600 text-white border-indigo-600 shadow-xs"
                : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
            }`}
          >
            {filterInvoicesOnly ? "Showing Invoiced Only" : "Filter Invoiced Only"}
          </button>
          <button
            onClick={() => {
              setFilterAlertsOnly(!filterAlertsOnly);
              setPage(1);
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors border ${
              filterAlertsOnly
                ? "bg-red-600 text-white border-red-600 shadow-xs"
                : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
            }`}
          >
            {filterAlertsOnly ? "Showing Alerts Only" : "Filter Alerts Only"}
          </button>
          <button
            onClick={loadHealth}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 transition-colors disabled:opacity-50"
          >
            {loading ? "Evaluating…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-xs rounded-lg p-3">
          {error}
        </div>
      )}

      {/* KPI Cards — Pure Database-Driven Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-medium text-slate-500">Monitored Deals</p>
          <p className="text-2xl font-extrabold text-slate-900 mt-1">{totalDeals}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">{filterInvoicesOnly ? "Invoiced Pipeline" : "Total Pipeline"}</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-medium text-indigo-600">Invoiced Deals</p>
          <p className="text-2xl font-extrabold text-indigo-600 mt-1">{invoicedCount}</p>
          <p className="text-[10px] text-indigo-400 mt-0.5">Live Invoice Ledger</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-medium text-red-600">Active Alerts</p>
          <p className="text-2xl font-extrabold text-red-600 mt-1">{alertCount}</p>
          <p className="text-[10px] text-red-400 mt-0.5">Consensus Flags</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-medium text-rose-600">Payment Overdue</p>
          <p className="text-2xl font-extrabold text-rose-600 mt-1">{overdueCount}</p>
          <p className="text-[10px] text-rose-400 mt-0.5">Aging &gt;30 Days</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-medium text-purple-600">Discount Outliers</p>
          <p className="text-2xl font-extrabold text-purple-600 mt-1">{anomalyCount}</p>
          <p className="text-[10px] text-purple-400 mt-0.5">Robust z &gt; 3.5</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-medium text-amber-600">Stalled Deals</p>
          <p className="text-2xl font-extrabold text-amber-600 mt-1">{stalledCount}</p>
          <p className="text-[10px] text-amber-500 mt-0.5">Silence &gt; 7 Days</p>
        </div>
      </div>

      {/* Active Alerts Banner if any */}
      {alertCount > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2 text-red-900 font-bold text-xs">
            <span>⚠️ Attention Required: {alertCount} deal(s) flagged by Sentinel consensus or invoice aging</span>
          </div>
          <div className="space-y-1.5">
            {deals
              .filter((d) => d.alert)
              .slice(0, 3)
              .map((d) => (
                <div
                  key={d.quotation_id}
                  className="text-xs text-red-800 bg-white/70 p-2 rounded-lg border border-red-100 flex items-center justify-between"
                >
                  <span className="font-mono font-semibold">
                    #Q-{d.quotation_id} · {d.customer_name}
                  </span>
                  <span className="text-[11px] text-red-600">
                    {d.payment_overdue
                      ? `Payment overdue: ${d.days_overdue} days outstanding (${formatCurrency(d.total_outstanding)})`
                      : d.stalled
                      ? `Stalled for ${d.days_inactive} days`
                      : d.discount_anomaly
                      ? `Discount outlier (z=${d.robust_z})`
                      : "Delivery risk detected"}
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Deals Table */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900">Quotation Sentinel Registry</h3>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Real-time synchronization with Quotations, Invoices, and Payment transactions.
            </p>
          </div>
          <span className="text-xs text-slate-500">
            Showing {displayedDeals.length} of {totalDeals} quotations
          </span>
        </div>

        {loading ? (
          <div className="p-12 text-center text-xs text-slate-500">
            Scanning deals and invoice ledgers with Sentinel statistical models…
          </div>
        ) : displayedDeals.length === 0 ? (
          <div className="p-12 text-center text-xs text-slate-500">
            No quotations match the selected criteria.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase tracking-wider font-semibold">
                <tr>
                  <th className="px-4 py-3">Quote #</th>
                  <th className="px-4 py-3">Customer</th>
                  <th className="px-4 py-3">Rep</th>
                  <th className="px-4 py-3">Quote State</th>
                  <th className="px-4 py-3">Invoice Status</th>
                  <th className="px-4 py-3 text-right">Invoiced / Due</th>
                  <th className="px-4 py-3 text-center">Inactive</th>
                  <th className="px-4 py-3 text-center">Disc %</th>
                  <th className="px-4 py-3 text-center">Robust Z</th>
                  <th className="px-4 py-3 text-center">Detectors</th>
                  <th className="px-4 py-3 text-center">Sentinel</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {displayedDeals.map((d) => (
                  <tr key={d.quotation_id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 font-mono font-bold text-slate-900">
                      <Link
                        to={`/quotes/${d.quotation_id}`}
                        className="text-indigo-600 hover:underline"
                        title="View quote"
                      >
                        #Q-{d.quotation_id}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-semibold text-slate-800">{d.customer_name}</p>
                      <p className="text-[10px] text-slate-400 uppercase font-medium">{d.customer_tier}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{d.rep_name}</td>
                    <td className="px-4 py-3">
                      <StateBadge state={d.state} />
                    </td>
                    <td className="px-4 py-3">
                      {d.invoice_status === "paid" ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                          PAID
                        </span>
                      ) : d.invoice_status === "overdue" || d.payment_overdue ? (
                        <span
                          className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200"
                          title={`${d.days_overdue || 0}d overdue`}
                        >
                          OVERDUE ({d.days_overdue}d)
                        </span>
                      ) : d.invoice_status === "unpaid" ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-100 text-amber-800">
                          UNPAID
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] text-slate-400 bg-slate-100">
                          PRE-INVOICE
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right font-mono">
                      {d.invoice_count && d.invoice_count > 0 ? (
                        <div>
                          <span className="font-semibold text-slate-800">
                            {formatCurrency(d.total_invoiced)}
                          </span>
                          {Number(d.total_outstanding || 0) > 0 ? (
                            <span className="block text-[10px] text-rose-600 font-medium">
                              Due: {formatCurrency(d.total_outstanding)}
                            </span>
                          ) : (
                            <span className="block text-[10px] text-emerald-600 font-medium">
                              Fully Settled
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center font-mono">
                      <span className={d.days_inactive > 7 ? "text-amber-600 font-bold" : "text-slate-600"}>
                        {d.days_inactive}d
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center font-mono text-slate-700">
                      {d.discount_pct.toFixed(1)}%
                    </td>
                    <td className="px-4 py-3 text-center font-mono">
                      <span
                        className={
                          Math.abs(d.robust_z) > 3.5
                            ? "text-red-600 font-bold bg-red-50 px-1.5 py-0.5 rounded"
                            : "text-slate-600"
                        }
                      >
                        {d.robust_z.toFixed(2)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-1">
                        {d.payment_overdue && (
                          <span
                            className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-800 text-[10px] font-bold"
                            title="Invoice Payment Overdue (>30d)"
                          >
                            PO
                          </span>
                        )}
                        {d.stalled && (
                          <span
                            className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] font-bold"
                            title="Stalled Deal"
                          >
                            ST
                          </span>
                        )}
                        {d.discount_anomaly && (
                          <span
                            className="px-1.5 py-0.5 rounded bg-purple-100 text-purple-800 text-[10px] font-bold"
                            title="Discount Outlier"
                          >
                            DC
                          </span>
                        )}
                        {d.delivery_slippage && (
                          <span
                            className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 text-[10px] font-bold"
                            title="Delivery Feasibility Risk"
                          >
                            DL
                          </span>
                        )}
                        {d.isolation_forest_outlier && (
                          <span
                            className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-800 text-[10px] font-bold"
                            title="Isolation Forest Multivariate Flag"
                          >
                            iF
                          </span>
                        )}
                        {!d.payment_overdue &&
                          !d.stalled &&
                          !d.discount_anomaly &&
                          !d.delivery_slippage &&
                          !d.isolation_forest_outlier && (
                            <span className="text-slate-300">-</span>
                          )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {d.alert ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-800 border border-red-200">
                          ALERT
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-100 text-emerald-800">
                          HEALTHY
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => setSelectedDeal(d)}
                        className="text-xs font-semibold text-slate-700 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 px-2.5 py-1 rounded transition-colors"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-4">
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
            pageSizeOptions={[10, 15, 25, 50]}
          />
        </div>
      </div>

      {/* Inspector Modal */}
      {selectedDeal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full border border-slate-200 p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  Sentinel Diagnostics: #Q-{selectedDeal.quotation_id}
                </h3>
                <p className="text-xs text-slate-500">{selectedDeal.customer_name}</p>
              </div>
              <button
                onClick={() => setSelectedDeal(null)}
                className="text-slate-400 hover:text-slate-600 text-lg font-bold"
              >
                ×
              </button>
            </div>

            <div className="space-y-3 text-xs">
              {/* Invoice & Settlement Telemetry */}
              <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                <span className="text-slate-700 font-bold block mb-2">Invoice &amp; Settlement Telemetry:</span>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <span className="text-slate-500 block text-[10px]">Total Invoiced:</span>
                    <span className="font-mono font-bold text-slate-800">
                      {formatCurrency(selectedDeal.total_invoiced)}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">Paid to Date:</span>
                    <span className="font-mono font-bold text-emerald-700">
                      {formatCurrency(selectedDeal.total_paid)}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">Outstanding:</span>
                    <span className={`font-mono font-bold ${Number(selectedDeal.total_outstanding || 0) > 0 ? "text-rose-600" : "text-slate-700"}`}>
                      {formatCurrency(selectedDeal.total_outstanding)}
                    </span>
                  </div>
                </div>
                <div className="mt-2.5 pt-2 border-t border-slate-200/60 flex items-center justify-between text-[11px]">
                  <span className="text-slate-500">
                    Status: <strong className="uppercase text-slate-800">{selectedDeal.invoice_status || "none"}</strong>
                  </span>
                  {selectedDeal.payment_overdue && (
                    <span className="text-rose-600 font-bold">
                      ⚠️ Overdue by {selectedDeal.days_overdue} days
                    </span>
                  )}
                </div>
              </div>

              {/* Statistical Detectors */}
              <div className="grid grid-cols-2 gap-2 bg-slate-50 p-3 rounded-lg border border-slate-200">
                <div>
                  <span className="text-slate-500 block">Robust Z-Score:</span>
                  <span className="font-mono font-bold text-slate-800">
                    {selectedDeal.robust_z} (baseline: {selectedDeal.history_source})
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 block">Days Inactive:</span>
                  <span className="font-mono font-bold text-slate-800">
                    {selectedDeal.days_inactive} days
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 block">Detector Agreement:</span>
                  <span className="font-mono font-bold text-slate-800">
                    {selectedDeal.votes} votes
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 block">Consensus Verdict:</span>
                  <span className={`font-bold ${selectedDeal.alert ? "text-red-600" : "text-emerald-600"}`}>
                    {selectedDeal.alert ? "FLAGGED FOR REVIEW" : "HEALTHY"}
                  </span>
                </div>
              </div>

              <div>
                <span className="text-slate-700 font-bold block mb-1">Audit Explanations:</span>
                <ul className="list-disc pl-4 space-y-1 text-slate-600">
                  {selectedDeal.explanation.map((exp, i) => (
                    <li key={i}>{exp}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 flex justify-end gap-2">
              <Link
                to={`/quotes/${selectedDeal.quotation_id}`}
                className="bg-slate-900 hover:bg-slate-800 text-white px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors"
              >
                Go to Quote
              </Link>
              <button
                onClick={() => setSelectedDeal(null)}
                className="bg-slate-100 hover:bg-slate-200 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
