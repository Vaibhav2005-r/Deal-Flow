import { useEffect, useState } from "react";
import { api, type Quote } from "@/lib/api";
import { RiskBadge, StateBadge } from "./components";

export default function QuoteList() {
  const [quotes, setQuotes] = useState<Quote[]>([]);

  useEffect(() => {
    api.get<Quote[]>("/api/quotes").then(setQuotes).catch(() => setQuotes([]));
  }, []);

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-slate-900">Quotations</h2>
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2 font-medium">#</th>
              <th className="px-4 py-2 font-medium">Customer</th>
              <th className="px-4 py-2 font-medium">State</th>
              <th className="px-4 py-2 font-medium">Risk</th>
              <th className="px-4 py-2 font-medium text-right">Lines</th>
              <th className="px-4 py-2 font-medium text-right">Net</th>
              <th className="px-4 py-2 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {quotes.slice(0, 40).map((q) => (
              <tr key={q.id} className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
                <td className="px-4 py-2 text-slate-500 font-mono font-medium">#{q.id}</td>
                <td className="px-4 py-2 font-medium text-slate-800">{q.customer_name}</td>
                <td className="px-4 py-2"><StateBadge state={q.state} /></td>
                <td className="px-4 py-2">
                  <RiskBadge score={q.risk_score ? Number(q.risk_score) : null} />
                </td>
                <td className="px-4 py-2 text-right">{q.totals.line_count}</td>
                <td className="px-4 py-2 text-right tabular-nums font-semibold text-slate-900">
                  {new Intl.NumberFormat("en-IN").format(Number(q.totals.net_total))}
                </td>
                <td className="px-4 py-2 text-right">
                  <button
                    onClick={() => {
                      const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
                      const token = localStorage.getItem("df360.internal.token");
                      fetch(`${BASE}/api/quotes/${q.id}/export/pdf`, {
                        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
                      })
                        .then((res) => res.blob())
                        .then((blob) => {
                          const link = document.createElement("a");
                          link.href = URL.createObjectURL(blob);
                          link.download = `quotation_${q.id}.pdf`;
                          link.click();
                        })
                        .catch((err) => alert("Failed to download PDF: " + err.message));
                    }}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 px-2.5 py-1 rounded transition-colors"
                  >
                    <span>📄</span> PDF
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
