import { useEffect, useState } from "react";
import { api, type DiscountConfig as Config } from "@/lib/api";
import { ErrorBanner, PageHeader } from "./components";

/** Screen 18 — Discount tiers and approval chains.
 *
 *  This is the governance configuration surface: editing it changes how every
 *  future quotation is scored. The server validates before it saves, so the
 *  UI shows what would be rejected rather than pretending a bad config is fine.
 */
export default function DiscountConfig() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [tierCaps, setTierCaps] = useState<Record<string, string>>({});
  const [catCaps, setCatCaps] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function hydrate(c: Config) {
    setCfg(c);
    setTierCaps(Object.fromEntries(c.tier_ceilings.map((t) => [t.tier, t.ceiling_pct])));
    setCatCaps(Object.fromEntries(
      c.category_ceilings.map((c2) => [`${c2.tier}|${c2.category}`, c2.ceiling_pct]),
    ));
  }

  useEffect(() => {
    api.get<Config>("/api/admin/discount-config")
      .then(hydrate)
      .catch((e) => setError(String(e.message)));
  }, []);

  if (error && !cfg) return <ErrorBanner error={error} />;
  if (!cfg) return <p className="text-sm text-slate-400">Loading…</p>;

  /** Mirrors the server's invariant so the rep sees it before pressing save. */
  const violations = cfg.category_ceilings
    .filter((c) => {
      const cap = Number(tierCaps[c.tier] ?? 0);
      return Number(catCaps[`${c.tier}|${c.category}`] ?? 0) > cap;
    })
    .map((c) => `${c.tier}/${c.category}`);

  async function save() {
    setBusy(true); setError(null); setSaved(null);
    try {
      const body = {
        tier_ceilings: Object.entries(tierCaps).map(([tier, ceiling_pct]) => ({
          tier, ceiling_pct,
        })),
        category_ceilings: cfg!.category_ceilings.map((c) => ({
          tier: c.tier,
          category: c.category,
          ceiling_pct: catCaps[`${c.tier}|${c.category}`] ?? c.ceiling_pct,
          floor_margin_pct: c.floor_margin_pct,
        })),
      };
      hydrate(await api.put<Config>("/api/admin/discount-config", body));
      setSaved("Configuration saved. Future quotations score against these ceilings.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Discount tiers & approval chains"
        subtitle="The ceilings and score bands every quotation is governed by."
        actions={
          <button
            onClick={save}
            disabled={busy || violations.length > 0}
            data-testid="save-config"
            className="bg-slate-900 text-white rounded px-4 py-1.5 text-sm font-medium disabled:opacity-40"
          >
            {busy ? "Saving…" : "Save configuration"}
          </button>
        }
      />

      <ErrorBanner error={error} />
      {saved && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded px-3 py-2">
          {saved}
        </div>
      )}
      {violations.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 text-sm rounded px-3 py-2">
          A category ceiling cannot exceed its tier cap — <code>min()</code> could never
          select it, so the quote builder would advertise a discount the engine
          refuses. Fix: {violations.join(", ")}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <section className="bg-white border border-slate-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-slate-700">Tier discount ceilings</h3>
          <p className="text-xs text-slate-500 mb-3">
            The most a customer of this tier may ever receive, whatever the category.
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200">
                <th className="py-1.5 font-medium">Tier</th>
                <th className="py-1.5 font-medium text-right">Max discount</th>
              </tr>
            </thead>
            <tbody>
              {cfg.tier_ceilings.map((t) => (
                <tr key={t.tier} className="border-b border-slate-100">
                  <td className="py-1.5 capitalize font-medium text-slate-700">{t.tier}</td>
                  <td className="py-1.5 text-right">
                    <input
                      type="number" min={0} max={100} step="0.5"
                      value={tierCaps[t.tier] ?? ""}
                      data-testid={`tier-${t.tier}`}
                      onChange={(e) =>
                        setTierCaps({ ...tierCaps, [t.tier]: e.target.value })
                      }
                      className="border border-slate-300 rounded px-2 py-1 text-sm w-24 text-right"
                    /> %
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="bg-white border border-slate-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-slate-700">Approval chains</h3>
          <p className="text-xs text-slate-500 mb-3">
            Which blended-risk band routes to whom.
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200">
                <th className="py-1.5 font-medium">Score band</th>
                <th className="py-1.5 font-medium">Requires</th>
              </tr>
            </thead>
            <tbody>
              {cfg.approval_chains.map((r) => (
                <tr key={r.min_score} className="border-b border-slate-100">
                  <td className="py-1.5 tabular-nums">
                    {Number(r.min_score).toFixed(0)}–{Number(r.max_score).toFixed(0)}
                  </td>
                  <td className="py-1.5">{r.label}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-slate-400 mt-3">
            A single line more than {cfg.engine_thresholds.hard_stop_excess_pp}pp over its
            ceiling routes to Finance regardless of score.
          </p>
        </section>
      </div>

      <section className="bg-white border border-slate-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-slate-700">Category discount ceilings</h3>
        <p className="text-xs text-slate-500 mb-3">
          Per-category rules. The engine scores against{" "}
          <code>min(tier, category)</code> — the effective column.
        </p>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-1.5 font-medium">Tier</th>
              <th className="py-1.5 font-medium">Category</th>
              <th className="py-1.5 font-medium text-right">Category max</th>
              <th className="py-1.5 font-medium text-right">Tier cap</th>
              <th className="py-1.5 font-medium text-right">Effective</th>
              <th className="py-1.5 font-medium text-right">Floor margin</th>
            </tr>
          </thead>
          <tbody>
            {cfg.category_ceilings.map((c) => {
              const key = `${c.tier}|${c.category}`;
              const cap = Number(tierCaps[c.tier] ?? 0);
              const cat = Number(catCaps[key] ?? 0);
              const over = cat > cap;
              const effective = Math.min(cap, cat);
              return (
                <tr key={key} className={`border-b border-slate-100 ${over ? "bg-amber-50" : ""}`}>
                  <td className="py-1.5 capitalize text-slate-700">{c.tier}</td>
                  <td className="py-1.5">{c.category}</td>
                  <td className="py-1.5 text-right">
                    <input
                      type="number" min={0} max={100} step="0.5"
                      value={catCaps[key] ?? ""}
                      data-testid={`cat-${c.tier}-${c.category}`}
                      onChange={(e) => setCatCaps({ ...catCaps, [key]: e.target.value })}
                      className="border border-slate-300 rounded px-2 py-1 text-sm w-20 text-right"
                    />
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-slate-500">{cap}</td>
                  <td className={`py-1.5 text-right tabular-nums font-medium ${
                    over ? "text-amber-700" : "text-slate-900"}`}>
                    {effective}
                    {cap < cat && <span className="text-[10px] text-slate-400"> tier</span>}
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-slate-500">
                    {Number(c.floor_margin_pct).toFixed(0)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
