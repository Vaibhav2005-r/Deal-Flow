import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AmountDue,
  type BillingDetailOut,
  type FulfillmentOut,
  type InvoicesOut,
  type Quote,
  type StockRow,
} from "@/lib/api";
import { StateBadge } from "./components";

import { money } from "./components";



/**
 * Phase 4 — the post-approval pipeline: allocate → invoice → collect.
 * Each button fires one state-machine event (§7); the guards live server-side,
 * so an illegal move surfaces as an error rather than being hidden in the UI.
 */
export default function Pipeline() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [fulfillment, setFulfillment] = useState<FulfillmentOut | null>(null);
  const [invoices, setInvoices] = useState<InvoicesOut | null>(null);
  const [due, setDue] = useState<AmountDue | null>(null);
  const [billing, setBilling] = useState<BillingDetailOut | null>(null);
  const [stock, setStock] = useState<StockRow[]>([]);
  const [overriding, setOverriding] = useState(false);
  const [split, setSplit] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const loadQuotes = useCallback(() => {
    api.get<Quote[]>("/api/quotes").then(setQuotes).catch(() => setQuotes([]));
  }, []);
  useEffect(loadQuotes, [loadQuotes]);

  const loadDetail = useCallback((id: number) => {
    Promise.all([
      api.get<FulfillmentOut>(`/api/quotes/${id}/fulfillment`),
      api.get<InvoicesOut>(`/api/quotes/${id}/invoices`),
      api.get<AmountDue>(`/api/quotes/${id}/amount-due`),
      api.get<BillingDetailOut>(`/api/quotes/${id}/billing-detail`),
      api.get<StockRow[]>("/api/fulfillment/stock"),
    ]).then(([f, i, d, b, st]) => {
      setFulfillment(f); setInvoices(i); setDue(d); setBilling(b); setStock(st);
      setOverriding(false); setSplit({});
    }).catch((e) => setError(String(e.message)));
  }, []);

  function select(id: number) {
    setSelected(id); setError(null); setNote(null); loadDetail(id);
  }

  async function act(path: string, label: string, body?: unknown) {
    if (!selected) return;
    setError(null); setNote(null);
    try {
      const res = await api.post<Record<string, unknown>>(`/api/quotes/${selected}${path}`, body ?? {});
      setNote(`${label}: ${JSON.stringify(res.state ?? res.fully_paid ?? "ok")}`);
      loadQuotes(); loadDetail(selected);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const quote = quotes.find((q) => q.id === selected);
  const warehouses = Array.from(
    new Map(stock.map((s) => [s.warehouse, s])).values(),
  );

  /** Screen 8's manual override: the operator names the split themselves.
   *  The server still refuses one that does not cover demand or exceeds
   *  available stock — a costlier plan is their call, an impossible one is not. */
  async function applyOverride() {
    if (!selected || !fulfillment) return;
    setError(null); setNote(null);
    const allocations = Object.entries(split)
      .filter(([, v]) => Number(v) > 0)
      .map(([key, v]) => {
        const [productId, warehouse] = key.split("|");
        const row = stock.find((s) => s.warehouse === warehouse);
        return {
          product_id: Number(productId),
          warehouse_id: warehouse === "backorder" ? null : (row?.warehouse_id ?? null),
          qty: Number(v),
        };
      });
    try {
      const res = await api.post<{ total_cost: string; shipment_count: number }>(
        `/api/quotes/${selected}/fulfillment/override`, { allocations },
      );
      setNote(`Override applied — ${res.shipment_count} shipment(s), cost ${res.total_cost}`);
      loadDetail(selected);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function subscriptionAction(path: string, body: unknown, label: string) {
    if (!selected) return;
    setError(null); setNote(null);
    try {
      await api.post(`/api/quotes/${selected}${path}`, body);
      setNote(label);
      loadDetail(selected);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  let isFinanceOrAdmin = false;
  try {
    const raw = localStorage.getItem("df360.internal.user");
    if (raw) {
      const u = JSON.parse(raw);
      isFinanceOrAdmin = u?.role === "finance" || u?.role === "admin";
    }
  } catch {
    isFinanceOrAdmin = false;
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-slate-900">Fulfillment &amp; billing</h2>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-sm rounded px-3 py-2" data-testid="pipeline-error">
          {error}
        </div>
      )}
      {note && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded px-3 py-2">
          {note}
        </div>
      )}

      <section className="bg-white border border-slate-200 rounded-lg p-4">
        <label className="text-sm">
          <span className="block text-slate-600 mb-1">Quotation</span>
          <select
            data-testid="pipeline-quote"
            className="border border-slate-300 rounded px-2 py-1.5 text-sm min-w-96"
            value={selected ?? ""}
            onChange={(e) => select(Number(e.target.value))}
          >
            <option value="">Select a quotation…</option>
            {quotes.map((q) => (
              <option key={q.id} value={q.id}>
                #{q.id} · {q.customer_name} · {q.state}
              </option>
            ))}
          </select>
        </label>

        {quote && (
          <div className="space-y-3 mt-4 pt-4 border-t border-slate-100">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold text-slate-500 mr-2">Current State:</span>
              <StateBadge state={quote.state} />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => act("/send-to-portal", "sent")}
                disabled={!quote.legal_events?.includes("send_to_portal")}
                title={
                  quote.legal_events?.includes("send_to_portal")
                    ? "Deliver quotation to customer portal for review"
                    : "Only available when quote is READY TO FULFILL"
                }
                className={`rounded px-3 py-1.5 text-xs font-semibold transition-all ${
                  quote.legal_events?.includes("send_to_portal")
                    ? "bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs"
                    : "bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed"
                }`}
              >
                1. Send to portal
              </button>

              <button
                onClick={() => act("/customer-confirm", "confirmed")}
                disabled={!quote.legal_events?.includes("customer_confirm")}
                title={
                  quote.legal_events?.includes("customer_confirm")
                    ? "Record customer confirmation / acceptance"
                    : "Only available when quote is SENT or UNDER NEGOTIATION"
                }
                className={`rounded px-3 py-1.5 text-xs font-semibold transition-all ${
                  quote.legal_events?.includes("customer_confirm")
                    ? "bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs"
                    : "bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed"
                }`}
              >
                2. Customer confirm
              </button>

              <button
                onClick={() => act("/plan-fulfillment", "planned")}
                data-testid="plan-fulfillment"
                disabled={!quote.legal_events?.includes("plan_fulfillment")}
                title={
                  quote.legal_events?.includes("plan_fulfillment")
                    ? "Run optimal warehouse solver to allocate stock across hubs"
                    : "Requires customer confirmation first (CONFIRMED state)"
                }
                className={`rounded px-3 py-1.5 text-xs font-semibold transition-all ${
                  quote.legal_events?.includes("plan_fulfillment")
                    ? "bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs"
                    : "bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed"
                }`}
              >
                3. Plan fulfillment
              </button>

              <button
                onClick={() => act("/generate-invoices", "invoiced")}
                data-testid="generate-invoices"
                disabled={!quote.legal_events?.includes("generate_invoices")}
                title={
                  quote.legal_events?.includes("generate_invoices")
                    ? "Generate one-time invoice and recurring billing schedules"
                    : "Requires fulfillment plan first (FULFILLING state)"
                }
                className={`rounded px-3 py-1.5 text-xs font-semibold transition-all ${
                  quote.legal_events?.includes("generate_invoices")
                    ? "bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs"
                    : "bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed"
                }`}
              >
                4. Generate invoices
              </button>

              {due && Number(due.outstanding) > 0 && quote.legal_events?.includes("record_payment") && (
                isFinanceOrAdmin ? (
                  <button
                    onClick={() => act("/payments", "paid", { amount: due.outstanding, method: "bank_transfer" })}
                    data-testid="record-payment"
                    className="bg-emerald-700 hover:bg-emerald-800 text-white rounded px-3 py-1.5 text-xs font-semibold shadow-xs"
                  >
                    5. Record payment of ₹{money(due.outstanding)}
                  </button>
                ) : (
                  <div className="flex items-center gap-2">
                    <button
                      disabled
                      className="bg-slate-100 text-slate-400 border border-slate-200 rounded px-3 py-1.5 text-xs font-semibold cursor-not-allowed"
                    >
                      5. Record payment (Locked)
                    </button>
                    <span className="text-xs text-amber-800 bg-amber-50 border border-amber-200 px-2 py-1 rounded">
                      🔒 Finance only: Sign out &amp; sign in as <strong>Aisha Karim · finance</strong> to collect payment
                    </span>
                  </div>
                )
              )}

              {quote.state === "PAID" && (
                <span className="text-xs font-semibold text-emerald-800 bg-emerald-50 px-2.5 py-1 rounded border border-emerald-200">
                  ✓ Order complete &amp; fully settled
                </span>
              )}
            </div>

            <div className="text-[11px] text-slate-500 bg-slate-50 p-2 rounded border border-slate-200">
              <span className="font-semibold text-slate-700">Lifecycle flow: </span>
              <span className={quote.state === "READY_TO_FULFILL" ? "text-indigo-600 font-bold" : ""}>Ready to Fulfill</span> →{" "}
              <span className={quote.state === "SENT" ? "text-indigo-600 font-bold" : ""}>Sent to Portal</span> →{" "}
              <span className={quote.state === "CONFIRMED" ? "text-indigo-600 font-bold" : ""}>Customer Confirmed</span> →{" "}
              <span className={quote.state === "FULFILLING" ? "text-indigo-600 font-bold" : ""}>Fulfilling</span> →{" "}
              <span className={quote.state === "INVOICED" ? "text-indigo-600 font-bold" : ""}>Invoiced</span> →{" "}
              <span className={quote.state === "PAID" ? "text-emerald-700 font-bold" : ""}>Paid</span>
            </div>
          </div>
        )}
      </section>

      {billing && (billing.one_time_lines.length > 0 || billing.recurring_lines.length > 0) && (
        <section className="bg-white border border-slate-200 rounded-lg p-4" data-testid="billing-detail">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Billing detail</h3>
          <div className="grid md:grid-cols-2 gap-5">
            <div>
              <h4 className="text-xs font-semibold text-slate-500 uppercase mb-1.5">
                One-time lines
              </h4>
              {billing.one_time_lines.length === 0 ? (
                <p className="text-sm text-slate-400">None.</p>
              ) : billing.one_time_lines.map((ln) => (
                <div key={ln.product_id} className="flex justify-between text-sm py-1 border-b border-slate-100">
                  <span>{ln.product_name} <span className="text-slate-400">×{ln.qty}</span></span>
                  <span className="tabular-nums">{money(ln.amount)}</span>
                </div>
              ))}
            </div>
            <div>
              <h4 className="text-xs font-semibold text-slate-500 uppercase mb-1.5">
                Recurring lines
              </h4>
              {billing.recurring_lines.length === 0 ? (
                <p className="text-sm text-slate-400">None.</p>
              ) : billing.recurring_lines.map((ln) => (
                <div key={ln.product_id} className="flex justify-between text-sm py-1 border-b border-slate-100">
                  <span>{ln.product_name} <span className="text-slate-400">×{ln.qty}</span></span>
                  <span className="tabular-nums">{money(ln.amount)}</span>
                </div>
              ))}
              {billing.subscription && (
                <div className="mt-3">
                  <p className="text-xs text-slate-500 mb-2">
                    Subscription #{billing.subscription.id} · next bill{" "}
                    <strong>{billing.subscription.next_bill_date}</strong> ·{" "}
                    {billing.subscription.status}
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => subscriptionAction(
                        "/subscription/pause",
                        { paused: billing!.subscription!.status !== "paused" },
                        "Subscription updated",
                      )}
                      data-testid="pause-subscription"
                      className="bg-amber-600 text-white rounded px-3 py-1 text-xs font-medium"
                    >
                      {billing.subscription.status === "paused" ? "Resume" : "Pause"}
                    </button>
                    <button
                      onClick={() => {
                        const reason = window.prompt("Reason for cancelling?");
                        if (reason?.trim()) {
                          subscriptionAction(
                            "/subscription/cancel", { reason },
                            "Cancelled — service continues to the end of the paid period",
                          );
                        }
                      }}
                      data-testid="cancel-subscription"
                      className="bg-red-700 text-white rounded px-3 py-1 text-xs font-medium"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {fulfillment?.plan && (
        <section className="bg-white border border-slate-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-2">
            Fulfillment plan · {fulfillment.plan.shipment_count} shipment(s) ·
            cost {money(fulfillment.plan.total_cost)}
          </h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200">
                <th className="py-1 font-medium">Product</th>
                <th className="py-1 font-medium">Warehouse</th>
                <th className="py-1 font-medium text-right">Qty</th>
              </tr>
            </thead>
            <tbody>
              {fulfillment.lines.map((ln, i) => (
                <tr key={i} className={`border-b border-slate-100 ${ln.is_backorder ? "bg-amber-50" : ""}`}>
                  <td className="py-1">{ln.product_name}</td>
                  <td className="py-1">
                    {ln.is_backorder
                      ? <span className="text-amber-700 text-xs font-semibold">BACKORDER</span>
                      : ln.warehouse}
                  </td>
                  <td className="py-1 text-right">{ln.qty}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="mt-4 flex items-center gap-2">
            <button
              onClick={() => setOverriding(!overriding)}
              data-testid="toggle-override"
              className="border border-slate-300 rounded px-3 py-1.5 text-xs font-medium"
            >
              {overriding ? "Keep suggested split" : "Manual override"}
            </button>
            {!overriding && (
              <span className="text-xs text-slate-400">
                Suggested split accepted — {fulfillment.plan.shipment_count} shipment(s)
              </span>
            )}
          </div>

          {overriding && (
            <div className="mt-3 border-t border-slate-100 pt-3" data-testid="override-form">
              <p className="text-xs text-slate-500 mb-2">
                Enter a quantity per warehouse for each product. The plan must still
                cover demand exactly and stay within available stock.
              </p>
              {Array.from(new Set(fulfillment.lines.map((l) => l.product_id))).map((pid) => {
                const name = fulfillment.lines.find((l) => l.product_id === pid)?.product_name;
                return (
                  <div key={pid} className="flex items-center gap-2 mb-1.5">
                    <span className="text-sm w-56 truncate">{name}</span>
                    {warehouses.map((w) => (
                      <label key={w.warehouse} className="text-xs text-slate-500">
                        {w.warehouse}
                        <input
                          type="number" min={0}
                          value={split[`${pid}|${w.warehouse}`] ?? ""}
                          data-testid={`split-${pid}-${w.warehouse}`}
                          onChange={(e) =>
                            setSplit({ ...split, [`${pid}|${w.warehouse}`]: e.target.value })
                          }
                          className="ml-1 border border-slate-300 rounded px-1.5 py-0.5 w-16 text-sm"
                        />
                      </label>
                    ))}
                  </div>
                );
              })}
              <button
                onClick={applyOverride}
                data-testid="apply-override"
                className="mt-2 bg-indigo-700 text-white rounded px-3 py-1.5 text-xs font-medium"
              >
                Apply override
              </button>
            </div>
          )}
        </section>
      )}

      {invoices && invoices.invoices.length > 0 && (
        <section className="bg-white border border-slate-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-2">Invoices</h3>
          {invoices.subscription && (
            <p className="text-xs text-slate-500 mb-3">
              Subscription #{invoices.subscription.id} · from{" "}
              {invoices.subscription.start_date} · next bill{" "}
              <strong>{invoices.subscription.next_bill_date}</strong> ·{" "}
              {invoices.subscription.status}
            </p>
          )}
          {invoices.invoices.map((inv) => (
            <div key={inv.id} className="border border-slate-100 rounded px-3 py-2 mb-2">
              <div className="flex justify-between text-sm">
                <span className="font-medium">
                  #{inv.id} · {inv.kind.replace("_", " ")}
                  {inv.period_key && <span className="text-slate-400"> · {inv.period_key}</span>}
                </span>
                <span className="tabular-nums">{money(inv.total)} · {inv.status}</span>
              </div>
              {inv.credit_notes.map((c, i) => (
                <p key={i} className="text-xs text-amber-700 mt-1">
                  credit note −{money(c.amount)} · {c.reason}
                </p>
              ))}
            </div>
          ))}
          {due && (
            <p className="text-sm text-slate-600 mt-2" data-testid="amount-due">
              billed {money(due.billed)} · credited {money(due.credited)} · due{" "}
              <strong>{money(due.amount_due)}</strong> · paid {money(due.paid)} ·
              outstanding <strong>{money(due.outstanding)}</strong>
            </p>
          )}
        </section>
      )}
    </div>
  );
}
