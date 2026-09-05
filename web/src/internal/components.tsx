import React from "react";
import type { ApprovalStep, Line } from "@/lib/api";

export const STATE_STYLES: Record<string, { bg: string; text: string; dot: string; border: string }> = {
  DRAFT: {
    bg: "bg-slate-50",
    text: "text-slate-700",
    dot: "bg-slate-400",
    border: "border-slate-200",
  },
  RISK_SCORED: {
    bg: "bg-blue-50",
    text: "text-blue-700",
    dot: "bg-blue-500",
    border: "border-blue-200",
  },
  PENDING_MANAGER: {
    bg: "bg-amber-50",
    text: "text-amber-800",
    dot: "bg-amber-500",
    border: "border-amber-200",
  },
  PENDING_FINANCE: {
    bg: "bg-orange-50",
    text: "text-orange-800",
    dot: "bg-orange-500",
    border: "border-orange-200",
  },
  APPROVED: {
    bg: "bg-emerald-50",
    text: "text-emerald-800",
    dot: "bg-emerald-500",
    border: "border-emerald-200",
  },
  REJECTED: {
    bg: "bg-rose-50",
    text: "text-rose-800",
    dot: "bg-rose-500",
    border: "border-rose-200",
  },
  RETURNED: {
    bg: "bg-amber-50",
    text: "text-amber-800",
    dot: "bg-amber-500",
    border: "border-amber-200",
  },
  READY_TO_FULFILL: {
    bg: "bg-emerald-50",
    text: "text-emerald-800",
    dot: "bg-emerald-500",
    border: "border-emerald-200",
  },
  SENT: {
    bg: "bg-indigo-50",
    text: "text-indigo-800",
    dot: "bg-indigo-500",
    border: "border-indigo-200",
  },
  UNDER_NEGOTIATION: {
    bg: "bg-purple-50",
    text: "text-purple-800",
    dot: "bg-purple-500",
    border: "border-purple-200",
  },
  FULFILLED: {
    bg: "bg-teal-50",
    text: "text-teal-800",
    dot: "bg-teal-500",
    border: "border-teal-200",
  },
};

export function StateBadge({ state }: { state: string }) {
  const normalized = state?.toUpperCase?.() ?? "DRAFT";
  const style = STATE_STYLES[normalized] ?? STATE_STYLES.DRAFT;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${style.bg} ${style.text} ${style.border} tracking-wide shadow-2xs whitespace-nowrap`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${style.dot} shrink-0`} />
      {normalized.replaceAll("_", " ")}
    </span>
  );
}

/** Risk band mirrors the routing thresholds: <20 low risk, <50 manager approval, >=50 finance approval */
export function RiskBadge({ score }: { score: number | null }) {
  if (score === null || score === undefined) {
    return <span className="text-slate-400 text-xs font-medium">—</span>;
  }
  
  let cls = "bg-emerald-50 text-emerald-700 border-emerald-200";
  let dotCls = "bg-emerald-500";
  let label = "Low Risk";

  if (score >= 50) {
    cls = "bg-rose-50 text-rose-700 border-rose-200";
    dotCls = "bg-rose-500";
    label = "High Risk";
  } else if (score >= 20) {
    cls = "bg-amber-50 text-amber-800 border-amber-200";
    dotCls = "bg-amber-500";
    label = "Med Risk";
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-semibold border ${cls} shadow-2xs whitespace-nowrap`}
      title={`BDRS Score: ${score.toFixed(1)} (${label})`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotCls} shrink-0`} />
      <span className="font-mono">BDRS {score.toFixed(1)}</span>
    </span>
  );
}

const nf = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
export const money = (v: string | number | null | undefined) => {
  if (v === null || v === undefined) return "0.00";
  return nf.format(Number(v));
};

export function LineTable({
  lines,
  onDelete,
}: {
  lines: Line[];
  onDelete?: (lineId: number) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-xs text-left">
        <thead>
          <tr className="bg-slate-50/80 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
            <th className="py-2.5 px-3">Product</th>
            <th className="py-2.5 px-3 text-right">Qty</th>
            <th className="py-2.5 px-3 text-right">List Price</th>
            <th className="py-2.5 px-3 text-right">Disc %</th>
            <th className="py-2.5 px-3 text-right">Ceiling</th>
            <th className="py-2.5 px-3 text-right">Margin</th>
            <th className="py-2.5 px-3 text-right">Net Value</th>
            <th className="py-2.5 px-3">Status / Breach</th>
            {onDelete && <th className="py-2.5 px-3 text-right">Action</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 font-sans">
          {lines.map((ln) => (
            <tr
              key={ln.id}
              className={`hover:bg-slate-50/70 transition-colors ${
                ln.breaches_ceiling ? "bg-rose-50/50" : ""
              }`}
            >
              <td className="py-2.5 px-3">
                <span className="font-semibold text-slate-900">{ln.product_name}</span>
                <span className="block text-[11px] text-slate-400">{ln.category}</span>
              </td>
              <td className="py-2.5 px-3 text-right font-medium text-slate-700">{ln.qty}</td>
              <td className="py-2.5 px-3 text-right tabular-nums text-slate-600">${money(ln.list_value)}</td>
              <td className="py-2.5 px-3 text-right tabular-nums font-semibold text-slate-800">
                {Number(ln.discount_pct).toFixed(1)}%
              </td>
              <td className="py-2.5 px-3 text-right tabular-nums text-slate-500">
                {ln.ceiling_pct_applied ? `${Number(ln.ceiling_pct_applied).toFixed(0)}%` : "—"}
              </td>
              <td className="py-2.5 px-3 text-right tabular-nums font-medium text-slate-700">
                {ln.margin_pct ? `${Number(ln.margin_pct).toFixed(1)}%` : "—"}
              </td>
              <td className="py-2.5 px-3 text-right tabular-nums font-bold text-slate-900">
                ${money(ln.net_value)}
              </td>
              <td className="py-2.5 px-3">
                {ln.breaches_ceiling ? (
                  <span
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-100 text-rose-700 font-semibold text-[11px]"
                    data-testid="breach"
                  >
                    +{Number(ln.excess_pp).toFixed(1)}pp breach
                  </span>
                ) : (
                  <span className="inline-flex items-center text-emerald-600 font-medium text-[11px]">
                    ✓ within policy
                  </span>
                )}
              </td>
              {onDelete && (
                <td className="py-2.5 px-3 text-right">
                  <button
                    type="button"
                    onClick={() => onDelete(ln.id)}
                    data-testid={`delete-line-${ln.id}`}
                    className="text-xs text-rose-600 hover:text-rose-800 font-semibold px-2 py-1 rounded hover:bg-rose-50 transition-colors cursor-pointer"
                    title="Remove line"
                  >
                    Delete
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const TRAIL_TONE: Record<string, { badge: string; text: string }> = {
  APPROVED: { badge: "bg-emerald-50 text-emerald-700 border-emerald-200", text: "Approved" },
  REJECTED: { badge: "bg-rose-50 text-rose-700 border-rose-200", text: "Rejected" },
  RETURNED: { badge: "bg-amber-50 text-amber-700 border-amber-200", text: "Returned for Edit" },
  VOIDED_BY_EDIT: { badge: "bg-slate-100 text-slate-400 border-slate-200", text: "Voided by Edit" },
  PENDING: { badge: "bg-blue-50 text-blue-700 border-blue-200", text: "Pending Decision" },
};

export function ApprovalTrail({ steps }: { steps: ApprovalStep[] }) {
  if (!steps || !steps.length) return null;
  const sorted = [...steps].sort((a, b) => a.id - b.id);
  
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-xs text-left" data-testid="approval-trail">
        <thead>
          <tr className="bg-slate-50/80 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
            <th className="py-2.5 px-3">Step & Reviewer</th>
            <th className="py-2.5 px-3">Decision</th>
            <th className="py-2.5 px-3">Timestamp</th>
            <th className="py-2.5 px-3">Review Notes</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {sorted.map((s) => {
            const tone = TRAIL_TONE[s.decision] ?? TRAIL_TONE.PENDING;
            return (
              <tr key={s.id} className="hover:bg-slate-50/70 transition-colors">
                <td className="py-2.5 px-3">
                  <span className="font-semibold text-slate-900">
                    {s.decided_by_name ?? "Awaiting Reviewer"}
                  </span>
                  <span className="block text-[11px] text-slate-400">
                    Step {s.step_index + 1} · {s.approver_role.replaceAll("_", " ")}
                  </span>
                </td>
                <td className="py-2.5 px-3">
                  <span className={`inline-block px-2 py-0.5 rounded text-[11px] font-semibold border ${tone.badge}`}>
                    {tone.text}
                  </span>
                </td>
                <td className="py-2.5 px-3 text-slate-500 tabular-nums">
                  {s.decided_at ? s.decided_at.slice(0, 16).replace("T", " ") : <span className="text-slate-400 italic">Pending</span>}
                </td>
                <td className="py-2.5 px-3 text-slate-700">
                  {s.reason ? s.reason : <span className="text-slate-400 italic">No notes provided</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Page header: title, subtitle, optional actions. */
export function PageHeader({
  title,
  subtitle,
  actions,
  badge,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  badge?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pb-4 border-b border-slate-200/80">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
          {badge}
        </div>
        {subtitle && <p className="text-xs sm:text-sm text-slate-500 mt-1 font-normal">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2.5 shrink-0 flex-wrap">{actions}</div>}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = "slate",
  icon,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: "slate" | "amber" | "emerald" | "red" | "indigo" | "blue";
  icon?: React.ReactNode;
}) {
  const tones: Record<string, { text: string; bg: string; border: string }> = {
    slate: { text: "text-slate-900", bg: "bg-slate-50", border: "border-slate-200" },
    amber: { text: "text-amber-700", bg: "bg-amber-50/60", border: "border-amber-200/80" },
    emerald: { text: "text-emerald-700", bg: "bg-emerald-50/60", border: "border-emerald-200/80" },
    red: { text: "text-rose-700", bg: "bg-rose-50/60", border: "border-rose-200/80" },
    indigo: { text: "text-indigo-700", bg: "bg-indigo-50/60", border: "border-indigo-200/80" },
    blue: { text: "text-[#1d72f2]", bg: "bg-blue-50/60", border: "border-blue-200/80" },
  };

  const selectedTone = tones[tone] ?? tones.slate;

  return (
    <div className="bg-white p-4 sm:p-5 rounded-xl border border-slate-200 shadow-2xs hover:shadow-xs transition-shadow flex flex-col justify-between">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{label}</p>
        {icon && <div className="text-slate-400">{icon}</div>}
      </div>
      <div className="mt-2">
        <p className={`text-2xl sm:text-3xl font-extrabold tracking-tight ${selectedTone.text}`}>
          {value}
        </p>
        {hint && <p className="text-[11px] text-slate-400 mt-1 font-medium">{hint}</p>}
      </div>
    </div>
  );
}

export function ErrorBanner({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="bg-rose-50 border border-rose-200 text-rose-800 text-xs font-medium rounded-lg p-3 flex items-start gap-2 shadow-2xs mb-4">
      <svg className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <span>{error}</span>
    </div>
  );
}

export function EmptyState({
  title = "No data found",
  description = "There are no records matching your current filter criteria.",
  action,
}: {
  title?: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="text-center py-12 px-4 rounded-xl border-2 border-dashed border-slate-200 bg-white/50 my-4">
      <div className="w-10 h-10 mx-auto mb-3 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
        </svg>
      </div>
      <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function EmptyRow({ colSpan, text }: { colSpan: number; text: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="py-10 text-center text-xs text-slate-400 font-medium">
        {text}
      </td>
    </tr>
  );
}

export function FilterTabs({
  options,
  value,
  onChange,
}: {
  options: { key: string; label: string; count?: number }[];
  value: string;
  onChange: (k: string) => void;
}) {
  return (
    <div className="flex items-center gap-1 bg-slate-200/70 p-1 rounded-lg w-fit overflow-x-auto no-scrollbar">
      {options.map((o) => {
        const active = value === o.key;
        return (
          <button
            key={o.key}
            onClick={() => onChange(o.key)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all whitespace-nowrap flex items-center gap-1.5 cursor-pointer ${
              active
                ? "bg-white text-slate-900 shadow-xs"
                : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/50"
            }`}
          >
            <span>{o.label}</span>
            {o.count !== undefined && (
              <span
                className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                  active ? "bg-slate-100 text-slate-800" : "bg-slate-300/60 text-slate-600"
                }`}
              >
                {o.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Pagination({
  page,
  pageSize,
  totalCount,
  totalPages,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [10, 20, 50, 100],
}: {
  page: number;
  pageSize: number;
  totalCount: number;
  totalPages: number;
  onPageChange: (newPage: number) => void;
  onPageSizeChange?: (newPageSize: number) => void;
  pageSizeOptions?: number[];
}) {
  if (totalCount === 0) return null;

  const start = Math.min((page - 1) * pageSize + 1, totalCount);
  const end = Math.min(page * pageSize, totalCount);

  // Generate page numbers window
  const pages: number[] = [];
  const maxButtons = 5;
  let startPage = Math.max(1, page - Math.floor(maxButtons / 2));
  let endPage = Math.min(totalPages, startPage + maxButtons - 1);
  if (endPage - startPage + 1 < maxButtons) {
    startPage = Math.max(1, endPage - maxButtons + 1);
  }
  for (let i = startPage; i <= endPage; i++) {
    pages.push(i);
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-white border border-slate-200 rounded-xl text-xs text-slate-600 shadow-2xs">
      <div className="flex items-center gap-3">
        <span>
          Showing <strong className="text-slate-900 font-semibold">{start}</strong> to{" "}
          <strong className="text-slate-900 font-semibold">{end}</strong> of{" "}
          <strong className="text-slate-900 font-semibold">{totalCount}</strong> entries
        </span>

        {onPageSizeChange && (
          <div className="flex items-center gap-1.5 ml-2 border-l border-slate-200 pl-3">
            <label className="text-slate-500">Per page:</label>
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="border border-slate-200 rounded-md px-2 py-1 bg-white text-slate-800 font-medium text-xs focus:outline-none focus:ring-1 focus:ring-[#1d72f2]"
            >
              {pageSizeOptions.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="px-2.5 py-1 rounded-md border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed font-medium transition-colors cursor-pointer"
        >
          ← Prev
        </button>

        {pages.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onPageChange(p)}
            className={`min-w-7 h-7 px-2 rounded-md font-semibold text-xs transition-colors cursor-pointer ${
              p === page
                ? "bg-[#1d72f2] text-white shadow-2xs"
                : "border border-slate-200 hover:bg-slate-50 text-slate-700"
            }`}
          >
            {p}
          </button>
        ))}

        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="px-2.5 py-1 rounded-md border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed font-medium transition-colors cursor-pointer"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
