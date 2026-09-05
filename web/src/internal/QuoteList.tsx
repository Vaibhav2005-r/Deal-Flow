import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Quote } from "@/lib/api";
import { EmptyRow, PageHeader, RiskBadge, StateBadge, money } from "./components";

/** Screen 3 — Quotations.
 *
 *  Board first, because the question a rep actually asks is "where is
 *  everything stuck?", which a flat table answers badly. The table view is one
 *  click away for scanning and sorting.
 */
const COLUMNS: { key: string; label: string; states: string[] }[] = [
  { key: "draft", label: "Draft", states: ["DRAFT"] },
  {
    key: "pending",
    label: "Pending approval",
    states: ["RISK_SCORED", "PENDING_MANAGER", "PENDING_FINANCE"],
  },
  { key: "approved", label: "Approved", states: ["READY_TO_FULFILL", "SENT"] },
  { key: "negotiation", label: "Negotiation", states: ["UNDER_NEGOTIATION"] },
  {
    key: "confirmed",
    label: "Confirmed",
    states: ["CONFIRMED", "FULFILLING", "INVOICED", "PAID"],
  },
];

export default function QuoteList() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [view, setView] = useState<"board" | "table">("board");

  useEffect(() => {
    api.get<Quote[]>("/api/quotes").then(setQuotes).catch(() => setQuotes([]));
  }, []);

  const byColumn = useMemo(() => {
    const map: Record<string, Quote[]> = {};
    for (const col of COLUMNS) {
      map[col.key] = quotes.filter((q) => col.states.includes(q.state));
    }
    return map;
  }, [quotes]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Quotations"
        subtitle="Every quotation in one pipeline view. Click a card to open it."
        actions={
          <>
            <button
              onClick={() => setView(view === "board" ? "table" : "board")}
              data-testid="toggle-view"
              className="border border-slate-300 rounded px-3 py-1.5 text-sm"
            >
              {view === "board" ? "Switch to table view" : "Switch to board view"}
            </button>
            <Link to="/build" className="bg-slate-900 text-white rounded px-3 py-1.5 text-sm font-medium">
              + New quotation
            </Link>
          </>
        }
      />

      {view === "board" ? (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3" data-testid="board">
          {COLUMNS.map((col) => (
            <div key={col.key} className="bg-slate-100/70 rounded-lg p-2">
              <div className="flex items-center justify-between px-1 pb-2">
                <h3 className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
                  {col.label}
                </h3>
                <span className="text-xs text-slate-400 tabular-nums">
                  {byColumn[col.key]?.length ?? 0}
                </span>
              </div>
              <div className="space-y-2 max-h-[32rem] overflow-y-auto">
                {(byColumn[col.key] ?? []).slice(0, 40).map((q) => (
                  <Link
                    key={q.id}
                    to={`/quotes/${q.id}`}
                    className="block bg-white border border-slate-200 rounded p-2.5 hover:border-slate-400"
                  >
                    <p className="text-sm font-medium text-slate-900 truncate">
                      {q.customer_name}
                    </p>
                    <p className="text-xs text-slate-400 mb-1.5">
                      #{q.id} · {q.totals.line_count} lines
                    </p>
                    <div className="flex items-center justify-between">
                      <span className="text-sm tabular-nums text-slate-700">
                        {money(q.totals.net_total as string)}
                      </span>
                      <RiskBadge score={q.risk_score ? Number(q.risk_score) : null} />
                    </div>
                  </Link>
                ))}
                {(byColumn[col.key]?.length ?? 0) === 0 && (
                  <p className="text-xs text-slate-400 px-1 py-3">Nothing here.</p>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
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
              </tr>
            </thead>
            <tbody>
              {quotes.length === 0 && <EmptyRow colSpan={6} text="No quotations yet." />}
              {quotes.slice(0, 60).map((q) => (
                <tr key={q.id} className="border-t border-slate-100">
                  <td className="px-4 py-2 text-slate-500">
                    <Link to={`/quotes/${q.id}`} className="hover:underline">{q.id}</Link>
                  </td>
                  <td className="px-4 py-2">{q.customer_name}</td>
                  <td className="px-4 py-2"><StateBadge state={q.state} /></td>
                  <td className="px-4 py-2">
                    <RiskBadge score={q.risk_score ? Number(q.risk_score) : null} />
                  </td>
                  <td className="px-4 py-2 text-right">{q.totals.line_count}</td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {money(q.totals.net_total as string)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
