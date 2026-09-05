import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type DealHealthAssessment } from "@/lib/api";
import { StateBadge } from "./components";

export default function HealthDashboard() {
  const [deals, setDeals] = useState<DealHealthAssessment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterAlertsOnly, setFilterAlertsOnly] = useState(false);
  const [selectedDeal, setSelectedDeal] = useState<DealHealthAssessment | null>(null);

  async function loadHealth() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<DealHealthAssessment[]>("/api/deal-health");
      setDeals(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load deal health");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadHealth();
  }, []);

  const totalDeals = deals.length;
  const alertCount = deals.filter((d) => d.alert).length;
  const stalledCount = deals.filter((d) => d.stalled).length;
  const anomalyCount = deals.filter((d) => d.discount_anomaly).length;
  const slippageCount = deals.filter((d) => d.delivery_slippage).length;

  const displayedDeals = filterAlertsOnly ? deals.filter((d) => d.alert) : deals;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Deal Health &amp; Sentinel Alerts</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Real-time statistical anomaly monitoring (§5.5) using Median Absolute Deviation and Isolation Forest.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setFilterAlertsOnly(!filterAlertsOnly)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors border ${
              filterAlertsOnly
                ? "bg-red-600 text-white border-red-600"
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

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-medium text-slate-500">Monitored Deals</p>
          <p className="text-2xl font-extrabold text-slate-900 mt-1">{totalDeals}</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-medium text-red-600">Active Alerts</p>
          <p className="text-2xl font-extrabold text-red-600 mt-1">{alertCount}</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-medium text-amber-600">Stalled Deals (&gt;7d)</p>
          <p className="text-2xl font-extrabold text-amber-600 mt-1">{stalledCount}</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-medium text-purple-600">Discount Outliers (z&gt;3.5)</p>
          <p className="text-2xl font-extrabold text-purple-600 mt-1">{anomalyCount}</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-medium text-blue-600">Fulfillment Risks</p>
          <p className="text-2xl font-extrabold text-blue-600 mt-1">{slippageCount}</p>
        </div>
      </div>

      {/* Active Alerts Banner if any */}
      {alertCount > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2 text-red-900 font-bold text-xs">
            <span>⚠️ Attention Required: {alertCount} deal(s) flagged by Sentinel consensus</span>
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
                    {d.stalled
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
          <h3 className="text-sm font-bold text-slate-900">Quotation Sentinel Registry</h3>
          <span className="text-xs text-slate-500">
            Showing {displayedDeals.length} of {totalDeals} quotations
          </span>
        </div>

        {loading ? (
          <div className="p-12 text-center text-xs text-slate-500">
            Scanning deals with Sentinel statistical models…
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
                  <th className="px-4 py-3">Status</th>
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
                        {!d.stalled && !d.discount_anomaly && !d.delivery_slippage && !d.isolation_forest_outlier && (
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
