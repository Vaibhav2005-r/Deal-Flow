import type { ApprovalStep, Line } from "@/lib/api";

export const STATE_STYLES: Record<string, string> = {
  DRAFT: "bg-slate-100 text-slate-700",
  RISK_SCORED: "bg-blue-100 text-blue-800",
  PENDING_MANAGER: "bg-amber-100 text-amber-800",
  PENDING_FINANCE: "bg-orange-100 text-orange-800",
  READY_TO_FULFILL: "bg-emerald-100 text-emerald-800",
  SENT: "bg-indigo-100 text-indigo-800",
  UNDER_NEGOTIATION: "bg-purple-100 text-purple-800",
};

export function StateBadge({ state }: { state: string }) {
  const cls = STATE_STYLES[state] ?? "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {state.replaceAll("_", " ")}
    </span>
  );
}

/** Risk band mirrors the routing thresholds in §5.1: <20 auto, <50 manager. */
export function RiskBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-slate-400 text-sm">—</span>;
  const cls =
    score >= 50 ? "bg-red-100 text-red-800"
    : score >= 20 ? "bg-amber-100 text-amber-800"
    : "bg-emerald-100 text-emerald-800";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${cls}`}>
      BDRS {score.toFixed(1)}
    </span>
  );
}

/**
 * The approval screen's core: a manager has to see WHICH line breached and by
 * how much, not just a score. Breaching lines are called out per row.
 */
export function LineTable({
  lines,
  onDelete,
}: {
  lines: Line[];
  onDelete?: (lineId: number) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-500 border-b border-slate-200">
            <th className="py-2 font-medium">Product</th>
            <th className="py-2 font-medium text-right">Qty</th>
            <th className="py-2 font-medium text-right">List</th>
            <th className="py-2 font-medium text-right">Disc %</th>
            <th className="py-2 font-medium text-right">Ceiling</th>
            <th className="py-2 font-medium text-right">Margin</th>
            <th className="py-2 font-medium text-right">Net</th>
            <th className="py-2 font-medium">Breach</th>
            {onDelete && <th className="py-2 font-medium text-right">Action</th>}
          </tr>
        </thead>
        <tbody>
          {lines.map((ln) => (
            <tr
              key={ln.id}
              className={`border-b border-slate-100 ${ln.breaches_ceiling ? "bg-red-50" : ""}`}
            >
              <td className="py-2 pr-2">
                {ln.product_name}
                <span className="block text-xs text-slate-400">{ln.category}</span>
              </td>
              <td className="py-2 text-right">{ln.qty}</td>
              <td className="py-2 text-right tabular-nums">{money(ln.list_value)}</td>
              <td className="py-2 text-right tabular-nums">{Number(ln.discount_pct).toFixed(1)}</td>
              <td className="py-2 text-right tabular-nums text-slate-500">
                {ln.ceiling_pct_applied ? Number(ln.ceiling_pct_applied).toFixed(0) : "—"}
              </td>
              <td className="py-2 text-right tabular-nums text-slate-500">
                {ln.margin_pct ? `${Number(ln.margin_pct).toFixed(1)}%` : "—"}
              </td>
              <td className="py-2 text-right tabular-nums">{money(ln.net_value)}</td>
              <td className="py-2">
                {ln.breaches_ceiling ? (
                  <span className="text-red-700 text-xs font-semibold" data-testid="breach">
                    +{Number(ln.excess_pp).toFixed(1)}pp over
                  </span>
                ) : (
                  <span className="text-slate-300 text-xs">ok</span>
                )}
              </td>
              {onDelete && (
                <td className="py-2 text-right">
                  <button
                    type="button"
                    onClick={() => onDelete(ln.id)}
                    data-testid={`delete-line-${ln.id}`}
                    className="text-xs text-red-600 hover:text-red-800 font-medium px-2 py-1 rounded hover:bg-red-50"
                    title="Remove line"
                  >
                    Remove
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

const TRAIL_TONE: Record<string, string> = {
  APPROVED: "text-emerald-700",
  REJECTED: "text-red-700",
  RETURNED: "text-amber-700",
  VOIDED_BY_EDIT: "text-slate-400 line-through",
  PENDING: "text-slate-900 font-medium",
};

/**
 * Screen 6's audit trail: User | Action | Date | Note.
 *
 * A step id is not a user and a null date is not "just now" — an approval
 * record that cannot say who decided and when is not an audit trail, so all
 * four columns are shown, with an explicit dash where a value genuinely does
 * not exist yet.
 */
export function ApprovalTrail({ steps }: { steps: ApprovalStep[] }) {
  if (!steps.length) return null;
  const sorted = [...steps].sort((a, b) => a.id - b.id);
  return (
    <table className="w-full text-sm" data-testid="approval-trail">
      <thead>
        <tr className="text-left text-slate-500 border-b border-slate-200">
          <th className="py-1.5 font-medium">User</th>
          <th className="py-1.5 font-medium">Action</th>
          <th className="py-1.5 font-medium">Date</th>
          <th className="py-1.5 font-medium">Note</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((s) => (
          <tr key={s.id} className="border-b border-slate-100">
            <td className="py-1.5">
              {s.decided_by_name ?? <span className="text-slate-300">—</span>}
              <span className="block text-xs text-slate-400">
                step {s.step_index + 1} · {s.approver_role.replaceAll("_", " ")}
              </span>
            </td>
            <td className={`py-1.5 ${TRAIL_TONE[s.decision] ?? "text-slate-700"}`}>
              {s.decision.replaceAll("_", " ").toLowerCase()}
            </td>
            <td className="py-1.5 text-slate-500 tabular-nums">
              {s.decided_at
                ? s.decided_at.slice(0, 10)
                : <span className="text-slate-300">awaiting</span>}
            </td>
            <td className="py-1.5 text-slate-600">
              {s.reason ?? <span className="text-slate-300">—</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const nf = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
export const money = (v: string | number) => nf.format(Number(v));

/** Page scaffold: title, one-line purpose, optional actions. */
export function PageHeader({
  title, subtitle, actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
        {subtitle && <p className="text-sm text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

export function StatCard({
  label, value, hint, tone = "slate",
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: "slate" | "amber" | "emerald" | "red" | "indigo";
}) {
  const tones: Record<string, string> = {
    slate: "text-slate-900",
    amber: "text-amber-700",
    emerald: "text-emerald-700",
    red: "text-red-700",
    indigo: "text-indigo-700",
  };
  return (
    <div className="bg-white p-4 rounded-lg border border-slate-200">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${tones[tone]}`}>{value}</p>
      {hint && <p className="text-[11px] text-slate-400 mt-0.5">{hint}</p>}
    </div>
  );
}

export function ErrorBanner({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="bg-red-50 border border-red-200 text-red-800 text-sm rounded px-3 py-2">
      {error}
    </div>
  );
}

export function EmptyRow({ colSpan, text }: { colSpan: number; text: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="py-8 text-center text-sm text-slate-400">
        {text}
      </td>
    </tr>
  );
}

export function FilterTabs({
  options, value, onChange,
}: {
  options: { key: string; label: string }[];
  value: string;
  onChange: (k: string) => void;
}) {
  return (
    <div className="flex gap-1">
      {options.map((o) => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={`px-3 py-1.5 text-xs font-medium rounded ${
            value === o.key
              ? "bg-slate-900 text-white"
              : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
          }`}
        >
          {o.label}
        </button>
      ))}
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
    <div className="flex flex-wrap items-center justify-between gap-3 px-3.5 py-2.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-600 shadow-2xs">
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
              className="border border-slate-300 rounded px-2 py-1 bg-white text-slate-800 font-medium text-xs focus:outline-none focus:border-indigo-500"
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
          className="px-2.5 py-1 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed font-medium transition-colors cursor-pointer"
        >
          ← Prev
        </button>

        {pages.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onPageChange(p)}
            className={`min-w-7 h-7 px-2 rounded font-semibold text-xs transition-colors cursor-pointer ${
              p === page
                ? "bg-indigo-600 text-white shadow-2xs"
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
          className="px-2.5 py-1 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed font-medium transition-colors cursor-pointer"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
