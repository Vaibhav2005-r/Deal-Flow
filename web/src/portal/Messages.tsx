import { Link } from "react-router-dom";
import { api, type PortalMessageSummary } from "@/lib/api";
import { useLiveData } from "@/lib/live";

/**
 * Screen 11, Messages tab.
 *
 * The per-quotation thread already exists; this is the cross-quotation view,
 * so a customer can see whether anyone replied without opening each quotation
 * in turn. Polls, because a reply arrives while this screen is open.
 */
export default function Messages() {
  const { data, error, initialLoading, lastUpdated } = useLiveData<PortalMessageSummary[]>(
    () => api.get<PortalMessageSummary[]>("/api/portal/messages", "portal"),
    [],
    8_000,
  );

  if (initialLoading) return <p className="text-sm text-slate-400">Loading…</p>;

  const messages = data ?? [];

  return (
    <div className="space-y-4" data-testid="portal-messages">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Messages</h2>
          <p className="text-sm text-slate-500">
            Every comment and counter-offer across your quotations.
          </p>
        </div>
        {lastUpdated && (
          <span className="text-xs text-slate-400">
            updated {lastUpdated.toLocaleTimeString()}
          </span>
        )}
      </div>

      {error && (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 text-sm rounded px-3 py-2">
          Could not refresh just now — showing the last known messages. {error}
        </div>
      )}

      {messages.length === 0 ? (
        <p className="text-sm text-slate-400">
          No messages yet. Open a quotation to comment on a line or propose a
          different discount.
        </p>
      ) : (
        <ul className="space-y-2">
          {messages.map((m) => (
            <li
              key={m.id}
              className={`border rounded-lg px-4 py-3 ${
                m.from_customer
                  ? "bg-indigo-50/60 border-indigo-200"
                  : "bg-white border-slate-200"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-600">
                  {m.from_customer ? "You" : m.author_name ?? "Your account manager"}
                  {m.line_label && (
                    <span className="text-slate-400"> · on {m.line_label}</span>
                  )}
                </span>
                <Link
                  to={`/portal/quotes/${m.quotation_id}`}
                  className="text-xs text-indigo-700 hover:underline"
                >
                  Quotation #{m.quotation_id}
                </Link>
              </div>
              <p className="text-sm text-slate-800">{m.body}</p>
              {m.counter_discount_pct && (
                <p className="text-xs text-indigo-800 mt-1 font-medium">
                  Proposed discount: {Number(m.counter_discount_pct).toFixed(1)}%
                </p>
              )}
              {m.created_at && (
                <p className="text-[11px] text-slate-400 mt-1">
                  {new Date(m.created_at).toLocaleString()}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
