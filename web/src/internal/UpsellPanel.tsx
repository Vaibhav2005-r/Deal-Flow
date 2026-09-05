import { useEffect, useState } from "react";
import { api, type SuggestionsOut } from "@/lib/api";

/**
 * Tier-1 output (§8): these are PROPOSALS. Accepting one adds a line through
 * the normal mutation path — the suggestion itself never writes anything.
 */
export default function UpsellPanel({
  quoteId,
  onAccept,
}: {
  quoteId: number;
  onAccept: (productId: number) => void;
}) {
  const [data, setData] = useState<SuggestionsOut | null>(null);

  useEffect(() => {
    api.get<SuggestionsOut>(`/api/quotes/${quoteId}/suggestions`)
      .then(setData)
      .catch(() => setData(null));
  }, [quoteId]);

  if (!data || !data.suggestions.length) return null;

  return (
    <section className="bg-white border border-slate-200 rounded-lg p-4" data-testid="upsell">
      <div className="flex items-baseline gap-2 mb-3">
        <h3 className="text-sm font-semibold text-slate-700">Often bought together</h3>
        <span className="text-xs text-slate-400">
          from {data.considered} mined associations · proposals only
        </span>
      </div>

      <ul className="space-y-2">
        {data.suggestions.map((s) => (
          <li
            key={s.product_id}
            className="flex items-center gap-3 border border-slate-100 rounded px-3 py-2"
          >
            <div className="flex-1">
              <p className="text-sm font-medium text-slate-900">
                {s.name}
                {s.is_promoted && (
                  <span className="ml-2 text-xs bg-indigo-100 text-indigo-800 px-1.5 py-0.5 rounded">
                    promoted
                  </span>
                )}
              </p>
              <p className="text-xs text-slate-500">
                lift {s.lift.toFixed(2)} · because {s.because_of} · order margin{" "}
                {s.current_margin_pct.toFixed(1)}% →{" "}
                <span className={s.margin_delta_if_added >= 0 ? "text-emerald-700" : "text-amber-700"}>
                  {s.projected_margin_pct.toFixed(1)}%
                </span>
              </p>
            </div>
            <button
              onClick={() => onAccept(s.product_id)}
              data-testid={`accept-${s.sku}`}
              className="bg-slate-700 text-white rounded px-3 py-1 text-xs font-medium"
            >
              Add
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
