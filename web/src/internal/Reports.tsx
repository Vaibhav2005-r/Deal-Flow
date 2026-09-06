import { useEffect, useState } from "react";
import { api, type ReportingMetrics } from "@/lib/api";
import { useAutoRefresh } from "@/lib/live";
import { currency } from "@/lib/money";
import SearchableSelect from "@/components/SearchableSelect";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export default function Reports() {
  // re-fetch on an interval and on tab focus, so the view tracks the database
  const tick = useAutoRefresh();
  const [period, setPeriod] = useState("all");
  const [selectedRep, setSelectedRep] = useState<string>("");
  const [selectedState, setSelectedState] = useState<string>("ALL");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");

  const [metrics, setMetrics] = useState<ReportingMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadMetrics() {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("period", period);
      if (selectedRep) params.set("rep_id", selectedRep);
      if (selectedState && selectedState !== "ALL") params.set("state", selectedState);
      if (selectedCategory && selectedCategory !== "all") params.set("category", selectedCategory);

      const data = await api.get<ReportingMetrics>(`/api/reports?${params.toString()}`);
      setMetrics(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load reporting analytics");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMetrics();
  }, [period, selectedRep, selectedState, selectedCategory, tick]);

  const formatMoney = (val: string | number) =>
    isNaN(Number(val)) ? String(val) : currency(val);

  function handleExport(format: "csv" | "xls") {
    const params = new URLSearchParams();
    params.set("format", format);
    params.set("period", period);
    if (selectedRep) params.set("rep_id", selectedRep);
    if (selectedState && selectedState !== "ALL") params.set("state", selectedState);
    if (selectedCategory && selectedCategory !== "all") params.set("category", selectedCategory);

    const token = localStorage.getItem("df360.internal.token");
    const url = `${BASE}/api/reports/export?${params.toString()}`;

    // Download file via authenticated fetch blob
    fetch(url, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
      .then((res) => res.blob())
      .then((blob) => {
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `dealflow_report_${period}.${format}`;
        link.click();
      })
      .catch((err) => alert(`Failed to download ${format.toUpperCase()}: ` + err.message));
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Sales Operations &amp; Governance Reports</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Multi-dimensional commercial pipeline analytics, conversion tracking, and data export.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleExport("csv")}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-700 hover:bg-emerald-800 text-white shadow-sm transition-colors"
          >
            <span>📥</span> Export CSV
          </button>
          <button
            onClick={() => handleExport("xls")}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-700 hover:bg-blue-800 text-white shadow-sm transition-colors"
          >
            <span>📊</span> Export Excel (.xls)
          </button>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
        <div>
          <label className="block font-semibold text-slate-600 mb-1">Time Horizon</label>
          <SearchableSelect
            value={period}
            onChange={(val) => setPeriod(String(val))}
            containerClassName="w-full"
            className="w-full bg-slate-50 border-slate-300"
            placeholder="Select period..."
            searchPlaceholder="Search horizon..."
            options={[
              { value: "all", label: "All Time" },
              { value: "30d", label: "Last 30 Days" },
              { value: "90d", label: "Last 90 Days" },
              { value: "1y", label: "Last Year" },
            ]}
          />
        </div>

        <div>
          <label className="block font-semibold text-slate-600 mb-1">Status Filter</label>
          <SearchableSelect
            value={selectedState}
            onChange={(val) => setSelectedState(String(val))}
            containerClassName="w-full"
            className="w-full bg-slate-50 border-slate-300"
            placeholder="Select state..."
            searchPlaceholder="Search state..."
            options={[
              { value: "ALL", label: "All States" },
              { value: "DRAFT", label: "DRAFT" },
              { value: "PENDING_MANAGER", label: "PENDING MANAGER" },
              { value: "PENDING_FINANCE", label: "PENDING FINANCE" },
              { value: "READY_TO_FULFILL", label: "READY TO FULFILL" },
              { value: "SENT", label: "SENT (Portal)" },
              { value: "UNDER_NEGOTIATION", label: "UNDER NEGOTIATION" },
              { value: "CONFIRMED", label: "CONFIRMED" },
              { value: "FULFILLING", label: "FULFILLING" },
              { value: "INVOICED", label: "INVOICED" },
              { value: "PAID", label: "PAID" },
            ]}
          />
        </div>

        <div>
          <label className="block font-semibold text-slate-600 mb-1">Product Category</label>
          <SearchableSelect
            value={selectedCategory}
            onChange={(val) => setSelectedCategory(String(val))}
            containerClassName="w-full"
            className="w-full bg-slate-50 border-slate-300"
            placeholder="Select category..."
            searchPlaceholder="Search category..."
            options={[
              { value: "all", label: "All Categories" },
              { value: "Hardware", label: "Hardware" },
              { value: "Software", label: "Software" },
              { value: "Service", label: "Service" },
              { value: "Subscription", label: "Subscription" },
            ]}
          />
        </div>

        <div>
          <label className="block font-semibold text-slate-600 mb-1">Sales Representative</label>
          <SearchableSelect
            value={selectedRep}
            onChange={(val) => setSelectedRep(String(val))}
            containerClassName="w-full"
            className="w-full bg-slate-50 border-slate-300"
            placeholder="Select representative..."
            searchPlaceholder="Search rep by name..."
            options={[
              { value: "", label: "All Representatives" },
              { value: "1", label: "Priya Raghavan" },
              { value: "2", label: "Daniel Okafor" },
              { value: "3", label: "Sofia Marchetti" },
            ]}
          />
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-xs rounded-lg p-3">
          {error}
        </div>
      )}

      {loading || !metrics ? (
        <div className="bg-white border border-slate-200 rounded-xl p-12 text-center text-xs text-slate-500">
          Compiling commercial pipeline telemetry…
        </div>
      ) : (
        <div className="space-y-6">
          {/* Executive Metrics Cards */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <p className="text-xs font-medium text-slate-500">Total Deals</p>
              <p className="text-2xl font-extrabold text-slate-900 mt-1">{metrics.total_quotes}</p>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <p className="text-xs font-medium text-slate-500">Net Pipeline Value</p>
              <p className="text-2xl font-extrabold text-slate-900 mt-1">{formatMoney(metrics.total_pipeline_value)}</p>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <p className="text-xs font-medium text-slate-500">Gross List Value</p>
              <p className="text-2xl font-extrabold text-slate-700 mt-1">{formatMoney(metrics.total_list_value)}</p>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <p className="text-xs font-medium text-indigo-600">Avg Discount Given</p>
              <p className="text-2xl font-extrabold text-indigo-600 mt-1">{metrics.avg_discount_pct.toFixed(1)}%</p>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <p className="text-xs font-medium text-emerald-600">Won Conversion Rate</p>
              <p className="text-2xl font-extrabold text-emerald-600 mt-1">{metrics.conversion_rate_pct.toFixed(1)}%</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Status Distribution */}
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900">Pipeline by Quotation Status</h3>
              <div className="space-y-2 text-xs">
                {Object.entries(metrics.status_distribution).map(([st, count]) => {
                  const pct = metrics.total_quotes > 0 ? (count / metrics.total_quotes) * 100 : 0;
                  return (
                    <div key={st} className="space-y-1">
                      <div className="flex justify-between text-slate-600 font-medium">
                        <span>{st}</span>
                        <span>{count} ({pct.toFixed(0)}%)</span>
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-indigo-600 h-2 rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Category Breakdown */}
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900">Net Revenue by Product Category</h3>
              <div className="space-y-2 text-xs">
                {metrics.category_breakdown.map((c) => {
                  const totalNet = Number(metrics.total_pipeline_value);
                  const catNet = Number(c.net_revenue);
                  const pct = totalNet > 0 ? (catNet / totalNet) * 100 : 0;
                  return (
                    <div key={c.category} className="space-y-1">
                      <div className="flex justify-between text-slate-600 font-medium">
                        <span>{c.category} · {c.units} units</span>
                        <span>{formatMoney(c.net_revenue)} ({pct.toFixed(0)}%)</span>
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-emerald-600 h-2 rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Rep Performance Table */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200">
              <h3 className="text-sm font-bold text-slate-900">Sales Representative Performance Leaderboard</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider">
                  <tr>
                    <th className="px-6 py-3">Representative</th>
                    <th className="px-6 py-3 text-center">Quotes Created</th>
                    <th className="px-6 py-3 text-center">Avg Discount Granted</th>
                    <th className="px-6 py-3 text-right">Total Realized Revenue</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {metrics.rep_performance.map((r) => (
                    <tr key={r.rep_id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-3.5 font-bold text-slate-800">{r.rep_name}</td>
                      <td className="px-6 py-3.5 text-center font-semibold text-slate-600">{r.quote_count}</td>
                      <td className="px-6 py-3.5 text-center font-mono font-medium text-indigo-700">
                        {r.avg_discount_pct.toFixed(1)}%
                      </td>
                      <td className="px-6 py-3.5 text-right font-bold text-slate-900">
                        {formatMoney(r.total_net)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
