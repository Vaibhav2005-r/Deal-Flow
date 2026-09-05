import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Quote } from "@/lib/api";
import { RiskBadge, StateBadge } from "./components";

export default function QuoteList() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    api.get<Quote[]>("/api/quotes").then(setQuotes).catch(() => setQuotes([]));
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Quotations</h2>
          <p className="text-sm text-slate-500">
            Click on any quote to view details or resume revision.
          </p>
        </div>
        <button
          onClick={() => navigate("/")}
          className="bg-slate-900 text-white rounded px-3 py-1.5 text-sm font-medium hover:bg-slate-800 transition"
        >
          + Create New Quote
        </button>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-3 font-medium">#</th>
              <th className="px-4 py-3 font-medium">Customer</th>
              <th className="px-4 py-3 font-medium">State</th>
              <th className="px-4 py-3 font-medium">Notice</th>
              <th className="px-4 py-3 font-medium">Risk</th>
              <th className="px-4 py-3 font-medium text-right">Lines</th>
              <th className="px-4 py-3 font-medium text-right">Net</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {quotes.slice(0, 40).map((q) => {
              const lastReturnedStep = q.approval_steps
                ?.slice()
                .reverse()
                .find((s) => s.decision === "RETURNED");
              const isRevisionNeeded = q.state === "DRAFT" && !!lastReturnedStep;

              return (
                <tr
                  key={q.id}
                  onClick={() => navigate(`/quotes/${q.id}`)}
                  className={`hover:bg-slate-50 cursor-pointer transition ${
                    isRevisionNeeded ? "bg-amber-50/50" : ""
                  }`}
                >
                  <td className="px-4 py-3 font-medium text-slate-700">#{q.id}</td>
                  <td className="px-4 py-3 font-medium text-slate-900">{q.customer_name}</td>
                  <td className="px-4 py-3"><StateBadge state={q.state} /></td>
                  <td className="px-4 py-3">
                    {isRevisionNeeded ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-900 border border-amber-300">
                        ⚠️ Needs Revision ({lastReturnedStep.approver_role})
                      </span>
                    ) : (
                      <span className="text-slate-400 text-xs">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <RiskBadge score={q.risk_score ? Number(q.risk_score) : null} />
                  </td>
                  <td className="px-4 py-3 text-right text-slate-600">{q.totals.line_count}</td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium text-slate-800">
                    {new Intl.NumberFormat("en-IN").format(Number(q.totals.net_total))}
                  </td>
                  <td className="px-4 py-3 text-right flex items-center justify-end gap-2">
                    {q.state === "DRAFT" ? (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/quotes/${q.id}`);
                        }}
                        className="text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 px-2.5 py-1 rounded transition"
                      >
                        {isRevisionNeeded ? "Revise & Resubmit →" : "Edit Draft →"}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/quotes/${q.id}`);
                        }}
                        className="text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 px-2 py-1 rounded transition"
                      >
                        View →
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
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
                      className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 px-2 py-1 rounded transition-colors"
                      title="Download PDF"
                    >
                      <span>📄</span> PDF
                    </button>
                  </td>
                </tr>
              );
            })}
            {quotes.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-slate-400">
                  No quotes found. Click "+ Create New Quote" to build your first quote.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
