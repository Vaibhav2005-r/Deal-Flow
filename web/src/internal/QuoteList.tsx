import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { api, type Quote } from "@/lib/api";
import { EmptyRow, PageHeader, Pagination, RiskBadge, StateBadge, currency, SearchableSelect } from "./components";
import { useAutoRefresh } from "@/lib/live";

interface ColumnDef {
  key: string;
  label: string;
  states: string[];
}

const COLUMNS: ColumnDef[] = [
  { key: "draft", label: "Draft", states: ["DRAFT"] },
  {
    key: "pending",
    label: "Pending Approval",
    states: ["RISK_SCORED", "PENDING_MANAGER", "PENDING_FINANCE"],
  },
  { key: "approved", label: "Approved", states: ["READY_TO_FULFILL", "SENT"] },
  { key: "negotiation", label: "Under Negotiation", states: ["UNDER_NEGOTIATION"] },
  {
    key: "confirmed",
    label: "Confirmed / Billed",
    states: ["CONFIRMED", "FULFILLING", "INVOICED", "PAID"],
  },
];

export default function QuoteList() {
  // re-fetch on an interval and on tab focus, so the view tracks the database
  const tick = useAutoRefresh();
  const shouldReduceMotion = useReducedMotion();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"board" | "table">("board");
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState<string>("all");
  const [sortBy, setSortBy] = useState<"recent" | "value_desc" | "value_asc">("recent");
  const [allQuotes, setAllQuotes] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    setLoading(true);
    const q = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      all_quotes: String(allQuotes),
    });
    api.getPaginated<Quote[]>(`/api/quotes?${q.toString()}`)
      .then((res) => {
        setQuotes(res.data);
        setTotalCount(res.totalCount);
        setTotalPages(res.totalPages);
      })
      .catch(() => setQuotes([]))
      .finally(() => setLoading(false));
  }, [allQuotes, page, pageSize, tick]);

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

    // Comprehensive Status & Financial filters
    if (filterType === "pending") {
      result = result.filter((item) =>
        ["RISK_SCORED", "PENDING_MANAGER", "PENDING_FINANCE"].includes(item.state)
      );
    } else if (filterType === "approved") {
      result = result.filter((item) => ["READY_TO_FULFILL", "SENT"].includes(item.state));
    } else if (filterType === "negotiation") {
      result = result.filter((item) => item.state === "UNDER_NEGOTIATION");
    } else if (filterType === "confirmed") {
      result = result.filter((item) =>
        ["CONFIRMED", "FULFILLING", "INVOICED", "PAID"].includes(item.state)
      );
    } else if (filterType === "high_value") {
      result = result.filter((item) => Number(item.totals?.net_total ?? 0) >= 500000);
    } else if (filterType === "high_discount") {
      result = result.filter(
        (item) =>
          Number(item.risk_score ?? 0) >= 20 ||
          item.lines?.some((ln) => Number(ln.discount_pct ?? 0) >= 15)
      );
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
  }, [quotes, search, filterType, sortBy]);

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
    <div className="space-y-5">
      {/* 1. Page Header */}
      <PageHeader
        title="Commercial Quotations"
        subtitle="Operational pipeline: inspect deal values, discount margins, BDRS risk scores, and approval states."
        actions={
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => setAllQuotes(!allQuotes)}
              data-testid="toggle-scope"
              className={`border rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors cursor-pointer ${
                allQuotes
                  ? "bg-slate-100 border-slate-300 text-slate-900"
                  : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {allQuotes ? "Showing all accounts" : "Showing assigned deals"}
            </button>
            <button
              type="button"
              onClick={() => setView(view === "board" ? "table" : "board")}
              data-testid="toggle-view"
              className="bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 rounded-lg px-3.5 py-1.5 text-xs font-semibold shadow-2xs transition-all cursor-pointer flex items-center gap-1.5"
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
          </div>
        }
      />

      {/* 2. Compact Enterprise Toolbar */}
      <div className="bg-white border border-slate-200 rounded-xl p-3.5 shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex flex-1 flex-wrap items-center gap-3">
          {/* Search Box */}
          <div className="relative w-full max-w-xs">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search customer, ID, or stage..."
              className="w-full pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-[#1d72f2] transition-all"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="absolute inset-y-0 right-0 pr-2.5 flex items-center text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                &times;
              </button>
            )}
          </div>

          {/* Status & Category Filter */}
          <SearchableSelect
            value={filterType}
            onChange={(val) => setFilterType(String(val))}
            placeholder="Filter quotations..."
            searchPlaceholder="Search filter options..."
            className="bg-slate-50 border-slate-200 text-xs text-slate-700 font-semibold"
            containerClassName="w-48"
            options={[
              { value: "all", label: "All Quotations" },
              { value: "pending", label: "Pending Approval" },
              { value: "approved", label: "Approved & Ready" },
              { value: "negotiation", label: "Under Negotiation" },
              { value: "confirmed", label: "Confirmed / Billed" },
              { value: "high_value", label: "High Value Deals (≥₹5L)" },
              { value: "high_discount", label: "High Discount / Risk Flags" },
            ]}
          />

          {/* Sort Selector */}
          <SearchableSelect
            value={sortBy}
            onChange={(val) => setSortBy(val as any)}
            placeholder="Sort by..."
            searchPlaceholder="Search sort options..."
            className="bg-slate-50 border-slate-200 text-xs text-slate-700 font-semibold"
            containerClassName="w-52"
            options={[
              { value: "recent", label: "Newest Quotations First" },
              { value: "value_desc", label: "Deal Value: High → Low" },
              { value: "value_asc", label: "Deal Value: Low → High" },
            ]}
          />
        </div>

        {/* Pipeline Summary Counter */}
        <div className="flex items-center gap-2 text-xs text-slate-500 shrink-0 self-end md:self-auto font-medium">
          {loading ? (
            <span className="flex items-center gap-1.5 text-slate-400">
              <span className="w-1.5 h-1.5 rounded-full bg-[#1d72f2] animate-pulse" />
              Loading pipeline data...
            </span>
          ) : (
            <>
              <span>Total: <strong className="text-slate-800 font-bold">{filteredQuotes.length}</strong> quotes</span>
              <span className="text-slate-300">·</span>
              <span>Value: <strong className="text-[#1d72f2] font-bold">{currency(totalPipelineValue)}</strong></span>
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
                className="bg-slate-100/70 border border-slate-200/80 rounded-xl p-3 flex flex-col min-h-[520px] max-h-[calc(100vh-220px)] shadow-2xs"
              >
                {/* Column Header */}
                <div className="flex items-center justify-between pb-2.5 mb-1 border-b border-slate-200/70">
                  <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    {col.label}
                  </h3>
                  <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-white text-slate-700 border border-slate-200 shadow-2xs tabular-nums">
                    {colQuotes.length}
                  </span>
                </div>

                {/* Cards Scrollable Area */}
                <div className="space-y-2.5 overflow-y-auto custom-scrollbar pr-1 flex-1 py-1">
                  {colQuotes.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 px-2 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg">
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
                            className="block bg-white border border-slate-200/90 hover:border-blue-300 rounded-xl p-3.5 shadow-2xs hover:shadow-xs transition-all group"
                          >
                            <div className="flex items-start justify-between gap-1">
                              <p className="text-xs font-bold text-slate-900 group-hover:text-[#1d72f2] transition-colors truncate">
                                {q.customer_name}
                              </p>
                            </div>

                            <p className="text-[11px] text-slate-400 mt-0.5 mb-2 font-medium">
                              #Q-{q.id} · {q.customer_tier} Tier · {q.totals?.line_count} line{q.totals?.line_count === 1 ? "" : "s"}
                            </p>

                            <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                              <span className="text-xs font-extrabold text-slate-900 tabular-nums">
                                {currency(netVal as string)}
                              </span>
                              <RiskBadge score={q.risk_score ? Number(q.risk_score) : null} />
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
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50/80 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-4 py-3">Quote #</th>
                  <th className="px-4 py-3">Customer & Tier</th>
                  <th className="px-4 py-3">Stage</th>
                  <th className="px-4 py-3">BDRS Risk</th>
                  <th className="px-4 py-3 text-right">Items</th>
                  <th className="px-4 py-3 text-right">Net Value</th>
                  <th className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-sans">
                {filteredQuotes.length === 0 ? (
                  <EmptyRow colSpan={7} text="No quotations match your filters." />
                ) : (
                  filteredQuotes.map((q) => (
                    <tr
                      key={q.id}
                      className="hover:bg-slate-50/80 transition-colors"
                    >
                      <td className="px-4 py-3 font-bold text-[#1d72f2]">
                        <Link to={`/quotes/${q.id}`} className="hover:underline">
                          #Q-{q.id}
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-semibold text-slate-900 block">{q.customer_name}</span>
                        <span className="text-[10px] text-slate-400 uppercase font-medium">{q.customer_tier} Tier</span>
                      </td>
                      <td className="px-4 py-3">
                        <StateBadge state={q.state} />
                      </td>
                      <td className="px-4 py-3">
                        <RiskBadge score={q.risk_score ? Number(q.risk_score) : null} />
                      </td>
                      <td className="px-4 py-3 text-right text-slate-500 font-medium">
                        {q.totals?.line_count}
                      </td>
                      <td className="px-4 py-3 text-right font-bold text-slate-900 tabular-nums">
                        {currency(q.totals?.net_total as string)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Link
                          to={`/quotes/${q.id}`}
                          className="px-2.5 py-1 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-md transition-colors shadow-2xs"
                        >
                          Review →
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

      {/* 5. Pagination */}
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
      />
    </div>
  );
}
