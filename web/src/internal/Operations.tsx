import { useState } from "react";
import { api, type PlanRow, type WarehouseRow } from "@/lib/api";
import { useLiveData } from "@/lib/live";
import { EmptyRow, ErrorBanner, PageHeader, StatCard, money } from "./components";

/**
 * §A4 and §A5 — warehouse and subscription-plan configuration.
 *
 * Both were seeded and working but had no screen, so an admin could not see or
 * change them without a database client. Creation is admin-only server-side;
 * the forms are shown to everyone who can reach the page and the API refuses
 * what the role may not do, so a non-admin sees the same truth rather than a
 * silently different one.
 */
export default function Operations() {
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const warehouses = useLiveData<WarehouseRow[]>(
    () => api.get<WarehouseRow[]>("/api/admin/warehouses"), [], 15_000,
  );
  const plans = useLiveData<PlanRow[]>(
    () => api.get<PlanRow[]>("/api/admin/subscription-plans"), [], 30_000,
  );

  const [wh, setWh] = useState({ code: "", name: "", unit_ship_cost: "2.5" });
  const [plan, setPlan] = useState({ name: "", interval: "monthly" });

  async function run(fn: () => Promise<unknown>, ok: string) {
    setError(null); setNote(null);
    try { await fn(); setNote(ok); warehouses.refresh(); plans.refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  const rows = warehouses.data ?? [];
  const planRows = plans.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Warehouses & plans"
        subtitle="Fulfillment locations and the recurring plans products can be sold on."
      />
      <ErrorBanner error={error} />
      {note && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded px-3 py-2">
          {note}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Warehouses" value={rows.length} />
        <StatCard label="Units on hand" value={rows.reduce((n, r) => n + r.units_on_hand, 0)} />
        <StatCard label="Units reserved" tone="indigo"
          value={rows.reduce((n, r) => n + r.units_reserved, 0)} />
        <StatCard label="Subscription plans" value={planRows.length} />
      </div>

      <section className="bg-white border border-slate-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Warehouses</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-2 font-medium">Code</th>
              <th className="py-2 font-medium">Name</th>
              <th className="py-2 font-medium text-right">Ship / unit</th>
              <th className="py-2 font-medium text-right">Fixed / shipment</th>
              <th className="py-2 font-medium text-right">SKUs</th>
              <th className="py-2 font-medium text-right">On hand</th>
              <th className="py-2 font-medium text-right">Reserved</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <EmptyRow colSpan={7} text="No warehouses configured." />}
            {rows.map((w) => (
              <tr key={w.id} className="border-b border-slate-100">
                <td className="py-2 font-medium">{w.code}</td>
                <td className="py-2">{w.name}</td>
                <td className="py-2 text-right tabular-nums">{money(w.unit_ship_cost)}</td>
                <td className="py-2 text-right tabular-nums">{money(w.ship_fixed_cost)}</td>
                <td className="py-2 text-right tabular-nums text-slate-500">{w.sku_count}</td>
                <td className="py-2 text-right tabular-nums">{w.units_on_hand}</td>
                <td className="py-2 text-right tabular-nums text-indigo-700">{w.units_reserved}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="flex flex-wrap items-end gap-2 mt-4 pt-3 border-t border-slate-100">
          {([["code", "Code"], ["name", "Name"], ["unit_ship_cost", "Ship / unit"]] as const).map(
            ([f, label]) => (
              <label key={f} className="text-sm">
                <span className="block text-slate-600 mb-1 text-xs">{label}</span>
                <input
                  value={wh[f]} data-testid={`wh-${f}`}
                  onChange={(e) => setWh({ ...wh, [f]: e.target.value })}
                  className="border border-slate-300 rounded px-2 py-1.5 text-sm w-32"
                />
              </label>
            ),
          )}
          <button
            data-testid="create-warehouse"
            disabled={!wh.code || !wh.name}
            onClick={() => run(
              () => api.post("/api/admin/warehouses", wh),
              `Warehouse ${wh.code.toUpperCase()} created.`,
            )}
            className="bg-slate-900 text-white rounded px-3 py-1.5 text-sm font-medium disabled:opacity-40"
          >
            Add warehouse
          </button>
        </div>
      </section>

      <section className="bg-white border border-slate-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Subscription plans</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-2 font-medium">Plan</th>
              <th className="py-2 font-medium">Interval</th>
              <th className="py-2 font-medium">Proration</th>
              <th className="py-2 font-medium">Cancellation</th>
            </tr>
          </thead>
          <tbody>
            {planRows.length === 0 && <EmptyRow colSpan={4} text="No plans configured." />}
            {planRows.map((p) => (
              <tr key={p.id} className="border-b border-slate-100">
                <td className="py-2">{p.name}</td>
                <td className="py-2 text-slate-600 capitalize">{p.interval}</td>
                <td className="py-2 text-slate-500">{p.proration_policy.replace("_", " ")}</td>
                <td className="py-2 text-slate-500">{p.cancellation_policy.replaceAll("_", " ")}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="flex flex-wrap items-end gap-2 mt-4 pt-3 border-t border-slate-100">
          <label className="text-sm">
            <span className="block text-slate-600 mb-1 text-xs">Plan name</span>
            <input
              value={plan.name} data-testid="plan-name"
              onChange={(e) => setPlan({ ...plan, name: e.target.value })}
              className="border border-slate-300 rounded px-2 py-1.5 text-sm w-52"
            />
          </label>
          <label className="text-sm">
            <span className="block text-slate-600 mb-1 text-xs">Interval</span>
            <select
              value={plan.interval} data-testid="plan-interval"
              onChange={(e) => setPlan({ ...plan, interval: e.target.value })}
              className="border border-slate-300 rounded px-2 py-1.5 text-sm"
            >
              {["monthly", "quarterly", "yearly"].map((i) => (
                <option key={i} value={i}>{i}</option>
              ))}
            </select>
          </label>
          <button
            data-testid="create-plan"
            disabled={!plan.name}
            onClick={() => run(
              () => api.post("/api/admin/subscription-plans", plan),
              `Plan "${plan.name}" created.`,
            )}
            className="bg-slate-900 text-white rounded px-3 py-1.5 text-sm font-medium disabled:opacity-40"
          >
            Add plan
          </button>
        </div>
      </section>
    </div>
  );
}
