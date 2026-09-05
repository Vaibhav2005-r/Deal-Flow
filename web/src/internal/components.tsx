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

const money = (v: string) =>
  new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Number(v));

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

export function ApprovalTrail({ steps }: { steps: ApprovalStep[] }) {
  if (!steps.length) return null;
  const tone: Record<string, string> = {
    APPROVED: "text-emerald-700",
    REJECTED: "text-red-700",
    RETURNED: "text-amber-700",
    VOIDED_BY_EDIT: "text-slate-400 line-through",
    PENDING: "text-slate-900 font-medium",
  };
  const sorted = [...steps].sort((a, b) => a.id - b.id);
  return (
    <ol className="text-sm space-y-1">
      {sorted.map((s) => (
        <li key={s.id} className={tone[s.decision] ?? "text-slate-700"}>
          Step {s.step_index + 1} ({s.approver_role.replaceAll("_", " ")}) — {s.decision}
          {s.reason && <span className="text-slate-500"> · "{s.reason}"</span>}
        </li>
      ))}
    </ol>
  );
}
