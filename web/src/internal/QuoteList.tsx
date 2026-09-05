import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { api, type Quote } from "@/lib/api";
import { EmptyRow, PageHeader, RiskBadge, StateBadge, money } from "./components";

interface ColumnDef {
  key: string;
  label: string;
  states: string[];
  tone?: string;
}

const COLUMNS: ColumnDef[] = [
  { key: "draft", label: "Draft", states: ["DRAFT"] },
  {
    key: "pending",
    label: "Pending Approval",
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
  const shouldReduceMotion = useReducedMotion();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"board" | "table">("board");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState<"recent" | "value_desc" | "value_asc">("recent");

  useEffect(() => {
    setLoading(true);
    api.get<Quote[]>("/api/quotes")
      .then(setQuotes)
      .catch(() => setQuotes([]))
      .finally(() => setLoading(false));
  }, []);

  // Filtered & Sorted quotes
  const filteredQuotes = useMemo(() => {
    let result = [...quotes];

    // Search filter
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter(
        (item) =>
          item.customer_name.toLowerCase().includes(q) ||
          String(item.id).includes(q) ||
          item.state.toLowerCase().includes(q)
      );
    }

    // Status filter
    if (statusFilter !== "all") {
      const col = COLUMNS.find((c) => c.key === statusFilter);
      if (col) {
        result = result.filter((item) => col.states.includes(item.state));
      }
    }

    // Sorting
    if (sortBy === "value_desc") {
      result.sort((a, b) => Number(b.totals?.net_total ?? 0) - Number(a.totals?.net_total ?? 0));
    } else if (sortBy === "value_asc") {
      result.sort((a, b) => Number(a.totals?.net_total ?? 0) - Number(b.totals?.net_total ?? 0));
    } else {
      result.sort((a, b) => b.id - a.id);
    }

    return result;
  }, [quotes, search, statusFilter, sortBy]);

  // Group quotes by Kanban columns
  const byColumn = useMemo(() => {
    const map: Record<string, Quote[]> = {};
    for (const col of COLUMNS) {
      map[col.key] = filteredQuotes.filter((q) => col.states.includes(q.state));
    }
    return map;
  }, [filteredQuotes]);

  const totalPipelineValue = useMemo(() => {
    return filteredQuotes.reduce((acc, q) => acc + (Number(q.totals?.net_total) || 0), 0);
  }, [filteredQuotes]);

  return (
    <div className="space-y-4">
      {/* 1. Page Header */}
      <PageHeader
        title="Quotations"
        subtitle="Every quotation in one pipeline view. Click a card to open it."
        actions={
          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setView(view === "board" ? "table" : "board")}
              data-testid="toggle-view"
              className="bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 hover:border-slate-300 rounded-lg px-3.5 py-1.5 text-xs font-semibold shadow-2xs transition-all cursor-pointer flex items-center gap-1.5"
            >
              {view === "board" ? (
                <>
                  <svg className="w-3.5 h-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                  </svg>
                  <span>Switch to table view</span>
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
                  </svg>
                  <span>Switch to board view</span>
                </>
              )}
            </button>
            <Link
              to="/build"
              className="bg-[#3b5bf6] hover:bg-[#2d4de6] text-white rounded-lg px-3.5 py-1.5 text-xs font-semibold shadow-xs hover:shadow transition-all flex items-center gap-1 cursor-pointer"
            >
              <span>+</span> New quotation
            </Link>
          </div>
        }
      />

      {/* 2. Compact Enterprise Toolbar */}
      <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex flex-1 items-center gap-3">
          {/* Search Box */}
          <div className="relative w-full max-w-sm">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search quotations by customer or ID..."
              className="w-full pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#3b5bf6]/20 focus:border-[#3b5bf6] transition-all"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute inset-y-0 right-0 pr-2.5 flex items-center text-slate-400 hover:text-slate-600"
              >
                &times;
              </button>
            )}
          </div>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 font-medium focus:outline-none focus:ring-2 focus:ring-[#3b5bf6]/20 focus:border-[#3b5bf6] transition-all cursor-pointer"
          >
            <option value="all">All Stages</option>
            {COLUMNS.map((col) => (
              <option key={col.key} value={col.key}>
                {col.label}
              </option>
            ))}
          </select>

          {/* Sort Selector */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 font-medium focus:outline-none focus:ring-2 focus:ring-[#3b5bf6]/20 focus:border-[#3b5bf6] transition-all cursor-pointer"
          >
            <option value="recent">Newest First</option>
            <option value="value_desc">Value: High &rarr; Low</option>
            <option value="value_asc">Value: Low &rarr; High</option>
          </select>
        </div>

        {/* Pipeline Summary Counter */}
        <div className="flex items-center gap-2 text-xs text-slate-500 shrink-0 self-end md:self-auto">
          {loading ? (
            <span className="flex items-center gap-1.5 text-slate-400">
              <span className="w-1.5 h-1.5 rounded-full bg-[#3b5bf6] animate-pulse" />
              Loading pipeline...
            </span>
          ) : (
            <>
              <span>Showing <strong className="text-slate-800">{filteredQuotes.length}</strong> quotations</span>
              <span className="text-slate-300">·</span>
              <span>Total: <strong className="text-[#3b5bf6]">{money(totalPipelineValue)}</strong></span>
            </>
          )}
        </div>
      </div>

      {/* 3. Main Views (Kanban or Table) */}
      {view === "board" ? (
        <div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5 items-start"
          data-testid="board"
        >
          {COLUMNS.map((col) => {
            const colQuotes = byColumn[col.key] ?? [];
            return (
              <div
                key={col.key}
                className="bg-slate-100/80 border border-slate-200/80 rounded-xl p-3 flex flex-col min-h-[500px] max-h-[calc(100vh-230px)] shadow-2xs"
              >
                {/* Column Header */}
                <div className="flex items-center justify-between pb-2.5 mb-1 border-b border-slate-200/60">
                  <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    {col.label}
                  </h3>
                  <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-white text-slate-700 border border-slate-200/90 shadow-2xs tabular-nums">
                    {colQuotes.length}
                  </span>
                </div>

                {/* Cards Scrollable Area */}
                <div className="space-y-2.5 overflow-y-auto custom-scrollbar pr-1 flex-1 py-1">
                  {colQuotes.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-10 px-2 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg">
                      <svg className="w-5 h-5 mb-1 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <span>No quotations in this stage</span>
                    </div>
                  ) : (
                    colQuotes.map((q) => {
                      const netVal = q.totals?.net_total ?? 0;
                      return (
                        <motion.div
                          key={q.id}
                          whileHover={shouldReduceMotion ? {} : { y: -2 }}
                          transition={{ duration: 0.15 }}
                        >
                          <Link
                            to={`/quotes/${q.id}`}
                            className="block bg-white border border-slate-200 hover:border-blue-300 rounded-xl p-3 shadow-2xs hover:shadow-md transition-all group"
                          >
                            <div className="flex items-start justify-between gap-1">
                              <p className="text-xs font-bold text-slate-900 group-hover:text-[#3b5bf6] transition-colors truncate">
                                {q.customer_name}
                              </p>
                            </div>

                            <p className="text-[11px] text-slate-400 mt-0.5 mb-2">
                              #{q.id} · {q.totals.line_count} line{q.totals.line_count === 1 ? "" : "s"}
                            </p>

                            <div className="flex items-center justify-between pt-1 border-t border-slate-100">
                              <span className="text-xs font-bold text-slate-800 tabular-nums">
                                {money(netVal as string)}
                              </span>
                              <div className="flex items-center gap-1.5">
                                <RiskBadge score={q.risk_score ? Number(q.risk_score) : null} />
                              </div>
                            </div>
                          </Link>
                        </motion.div>
                      );
                    })
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* 4. Table View */
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 text-slate-600 border-b border-slate-200">
                <tr>
                  <th className="px-4 py-3 font-semibold">Quote ID</th>
                  <th className="px-4 py-3 font-semibold">Customer</th>
                  <th className="px-4 py-3 font-semibold">Stage</th>
                  <th className="px-4 py-3 font-semibold">Risk Score</th>
                  <th className="px-4 py-3 font-semibold text-right">Lines</th>
                  <th className="px-4 py-3 font-semibold text-right">Net Value</th>
                  <th className="px-4 py-3 text-right font-semibold">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredQuotes.length === 0 ? (
                  <EmptyRow colSpan={7} text="No quotations match your filters." />
                ) : (
                  filteredQuotes.map((q) => (
                    <tr
                      key={q.id}
                      className="hover:bg-slate-50/80 transition-colors"
                    >
                      <td className="px-4 py-3 font-bold text-[#3b5bf6]">
                        <Link to={`/quotes/${q.id}`} className="hover:underline">
                          #{q.id}
                        </Link>
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-900">
                        {q.customer_name}
                      </td>
                      <td className="px-4 py-3">
                        <StateBadge state={q.state} />
                      </td>
                      <td className="px-4 py-3">
                        <RiskBadge score={q.risk_score ? Number(q.risk_score) : null} />
                      </td>
                      <td className="px-4 py-3 text-right text-slate-500 font-medium">
                        {q.totals.line_count}
                      </td>
                      <td className="px-4 py-3 text-right font-bold text-slate-900 tabular-nums">
                        {money(q.totals.net_total as string)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Link
                          to={`/quotes/${q.id}`}
                          className="px-2.5 py-1 text-[11px] font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-md transition-colors"
                        >
                          View &rarr;
                        </Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
