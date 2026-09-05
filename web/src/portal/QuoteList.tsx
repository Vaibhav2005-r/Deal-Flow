import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type PortalQuoteSummary } from "@/lib/api";
import { clearToken } from "@/lib/auth";

export default function QuoteList() {
  const [quotes, setQuotes] = useState<PortalQuoteSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const user = (() => {
    try {
      const raw = localStorage.getItem("df360.portal.user");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  })();

  function handleLogout() {
    clearToken("portal");
    localStorage.removeItem("df360.portal.user");
    navigate("/portal/login", { replace: true });
  }

  async function loadQuotes() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<PortalQuoteSummary[]>("/api/portal/quotes", "portal");
      setQuotes(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load quotations");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadQuotes();
  }, []);

  function formatCurrency(val: string | number) {
    const n = Number(val);
    return isNaN(n) ? String(val) : `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function renderStateBadge(state: string) {
    if (state === "SENT") {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-200">
          Awaiting Review
        </span>
      );
    }
    if (state === "UNDER_NEGOTIATION") {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
          Under Negotiation
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-800 border border-slate-200">
        {state}
      </span>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-6 py-4 shadow-sm">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold">
              DF
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-900 leading-tight">DealFlow360</h1>
              <p className="text-xs text-indigo-600 font-medium">Customer Portal</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-xs font-semibold text-slate-800">
                {user?.full_name ?? "Portal Contact"}
              </p>
              <p className="text-xs text-slate-500">Customer Account</p>
            </div>
            <button
              onClick={handleLogout}
              className="text-xs text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-md font-medium transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-slate-900">Your Quotations</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Review received quotations, comment on line items, and counter or confirm terms.
            </p>
          </div>
          <button
            onClick={loadQuotes}
            disabled={loading}
            className="text-xs font-medium text-indigo-600 hover:text-indigo-800 bg-indigo-50 hover:bg-indigo-100 px-3 py-1.5 rounded-md transition-colors"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {error && (
          <div className="p-4 mb-6 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {error}
          </div>
        )}

        {loading ? (
          <div className="bg-white border border-slate-200 rounded-xl p-12 text-center text-slate-500 text-sm">
            Loading your quotations…
          </div>
        ) : quotes.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-xl p-12 text-center">
            <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 mx-auto flex items-center justify-center text-lg font-bold mb-3">
              📋
            </div>
            <h3 className="text-sm font-semibold text-slate-800">No active quotations</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              You currently have no quotations pending review or negotiation. When your account representative shares a new proposal, it will appear here.
            </p>
          </div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                <tr>
                  <th className="px-6 py-3.5">Quotation #</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5 text-center">Items</th>
                  <th className="px-6 py-3.5 text-right">Net Proposal Total</th>
                  <th className="px-6 py-3.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {quotes.map((q) => (
                  <tr key={q.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 font-mono font-medium text-slate-900">
                      #Q-{q.id}
                    </td>
                    <td className="px-6 py-4">{renderStateBadge(q.state)}</td>
                    <td className="px-6 py-4 text-center text-slate-600">
                      {q.line_count} {q.line_count === 1 ? "item" : "items"}
                    </td>
                    <td className="px-6 py-4 text-right font-semibold text-slate-900">
                      {formatCurrency(q.net_total)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link
                        to={`/portal/quotes/${q.id}`}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 rounded-lg transition-colors shadow-sm"
                      >
                        Review & Negotiate →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
