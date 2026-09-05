import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
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
  const [searchParams, setSearchParams] = useSearchParams();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [selectedQuote, setSelectedQuote] = useState<Quote | null>(null);
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
    api.get<Quote[]>("/api/quotes?all_quotes=true&page_size=200").then(setQuotes).catch(() => setQuotes([]));
  }, []);
  useEffect(loadQuotes, [loadQuotes]);

  const loadDetail = useCallback((id: number) => {
    Promise.all([
      api.get<FulfillmentOut>(`/api/quotes/${id}/fulfillment`),
      api.get<InvoicesOut>(`/api/quotes/${id}/invoices`),
      api.get<AmountDue>(`/api/quotes/${id}/amount-due`),
      api.get<BillingDetailOut>(`/api/quotes/${id}/billing-detail`),
      api.get<StockRow[]>("/api/fulfillment/stock"),
      api.get<Quote>(`/api/quotes/${id}`),
    ]).then(([f, i, d, b, st, q]) => {
      setFulfillment(f); setInvoices(i); setDue(d); setBilling(b); setStock(st);
      setSelectedQuote(q);
      setOverriding(false); setSplit({});
    }).catch((e) => setError(String(e.message)));
  }, []);

  useEffect(() => {
    const qid = searchParams.get("id");
    if (qid) {
      const parsed = Number(qid);
      if (!isNaN(parsed) && parsed > 0 && parsed !== selected) {
        setSelected(parsed);
        setError(null);
        setNote(null);
        loadDetail(parsed);
      }
    }
  }, [searchParams, loadDetail, selected]);

  function select(id: number) {
    setSelected(id);
    setError(null);
    setNote(null);
    setSearchParams(id ? { id: String(id) } : {});
    if (id) loadDetail(id);
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

  const quote = quotes.find((q) => q.id === selected) || selectedQuote;
  const warehouses = Array.from(
    new Map(stock.map((s) => [s.warehouse, s])).values(),
  );

  function toggleOverride() {
    if (!overriding && fulfillment?.lines) {
      const initSplit: Record<string, string> = {};
      fulfillment.lines.forEach((l) => {
        const key = l.is_backorder || !l.warehouse ? `${l.product_id}|backorder` : `${l.product_id}|${l.warehouse}`;
        initSplit[key] = String(l.qty);
      });
      setSplit(initSplit);
    }
    setOverriding(!overriding);
  }

  async function checkBackorderConsolidation(productId: number) {
    if (!selected) return;
    setError(null); setNote(null);
    try {
      const res = await api.post<{
        product_id: number;
        open_backorders: number;
        outstanding_qty: number;
        available_qty: number;
        coverable_qty: number;
        proposed: boolean;
      }>(`/api/quotes/${selected}/fulfillment/consolidate/${productId}`, {});

      if (res.proposed && res.coverable_qty > 0) {
        setNote(`✓ Inbound stock detected! ${res.coverable_qty} units can now be consolidated. Proposal generated on outbox.`);
      } else {
        setNote(`Backorder check: ${res.outstanding_qty} units outstanding, ${res.available_qty} available in warehouses. Inbound receipt required.`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

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
            {selected && !quotes.some((q) => q.id === selected) && selectedQuote && (
              <option key={selectedQuote.id} value={selectedQuote.id}>
                #{selectedQuote.id} · {selectedQuote.customer_name} · {selectedQuote.state}
              </option>
            )}
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

              {quote.legal_events?.includes("rep_accepts_counter") && (
                <button
                  onClick={() => act("/accept-counter", "counter accepted")}
                  data-testid="accept-counter"
                  title="Accept customer's proposed counter discount, re-score, and update approval state"
                  className="rounded px-3 py-1.5 text-xs font-semibold bg-purple-600 hover:bg-purple-700 text-white shadow-xs transition-all"
                >
                  ⚡ Accept customer counter
                </button>
              )}

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

      {fulfillment?.plan && (() => {
        const backorderLines = fulfillment.lines.filter((l) => l.is_backorder || !l.warehouse);
        const shippedLines = fulfillment.lines.filter((l) => !l.is_backorder && l.warehouse);
        const uniqueWarehouses = Array.from(new Set(shippedLines.map((l) => l.warehouse!))).sort();
        const uniqueProductIds = Array.from(new Set(fulfillment.lines.map((l) => l.product_id)));

        return (
          <section className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-slate-900">
                    Fulfillment Plan &amp; Multi-Warehouse Allocation
                  </h3>
                  {fulfillment.plan.shipment_count > 1 ? (
                    <span className="inline-flex items-center gap-1 bg-purple-100 text-purple-800 border border-purple-200 text-xs px-2.5 py-0.5 rounded-full font-bold">
                      ⚡ Multi-Warehouse Split ({fulfillment.plan.shipment_count} Shipments)
                    </span>
                  ) : (
                    <span className="inline-flex items-center bg-blue-50 text-blue-800 border border-blue-200 text-xs px-2 py-0.5 rounded-full font-medium">
                      Single Warehouse
                    </span>
                  )}
                  {backorderLines.length > 0 && (
                    <span className="inline-flex items-center gap-1 bg-amber-100 text-amber-800 border border-amber-200 text-xs px-2.5 py-0.5 rounded-full font-bold">
                      ⚠️ Has Backorders
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Total Logistics Cost: <strong className="text-slate-800">₹{money(fulfillment.plan.total_cost)}</strong> ·
                  Shipments: <strong className="text-slate-800">{fulfillment.plan.shipment_count}</strong>
                </p>
              </div>

              <button
                onClick={toggleOverride}
                data-testid="toggle-override"
                className={`rounded px-3 py-1.5 text-xs font-semibold transition-all border ${
                  overriding
                    ? "bg-slate-100 hover:bg-slate-200 text-slate-700 border-slate-300"
                    : "bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border-indigo-200 shadow-2xs"
                }`}
              >
                {overriding ? "✕ Close Manual Override" : "✎ Manual Override Split"}
              </button>
            </div>

            {/* Grouped Warehouse Shipments Display */}
            {!overriding && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {uniqueWarehouses.map((whCode, idx) => {
                    const linesInWh = shippedLines.filter((l) => l.warehouse === whCode);
                    const totalQty = linesInWh.reduce((sum, l) => sum + l.qty, 0);
                    return (
                      <div key={whCode} className="border border-slate-200 rounded-lg p-3 bg-slate-50/50">
                        <div className="flex items-center justify-between border-b border-slate-200 pb-2 mb-2">
                          <div className="flex items-center gap-2">
                            <span className="w-5 h-5 rounded bg-indigo-600 text-white font-bold text-xs flex items-center justify-center">
                              {idx + 1}
                            </span>
                            <span className="font-bold text-xs text-slate-800 uppercase tracking-wide">
                              Shipment from {whCode} Hub
                            </span>
                          </div>
                          <span className="text-xs text-slate-500 font-medium">
                            {totalQty} {totalQty === 1 ? "unit" : "units"}
                          </span>
                        </div>
                        <ul className="divide-y divide-slate-100 text-xs">
                          {linesInWh.map((l, i) => (
                            <li key={i} className="py-1.5 flex justify-between items-center">
                              <span className="text-slate-800 font-medium">{l.product_name}</span>
                              <span className="font-mono bg-white border border-slate-200 px-2 py-0.5 rounded text-slate-700">
                                {l.qty}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    );
                  })}
                </div>

                {/* Backorder Management Section */}
                {backorderLines.length > 0 && (
                  <div className="border border-amber-300 bg-amber-50/70 rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-base">⚠️</span>
                        <div>
                          <h4 className="text-xs font-bold text-amber-900 uppercase tracking-wide">
                            Open Backorders (Awaiting Stock Inbound)
                          </h4>
                          <p className="text-[11px] text-amber-700">
                            These items could not be fulfilled from available warehouse stock.
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="bg-white border border-amber-200 rounded-md overflow-hidden">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-amber-100/60 border-b border-amber-200 text-amber-900 font-semibold text-left">
                            <th className="px-3 py-2">Product</th>
                            <th className="px-3 py-2 text-right">Backordered Qty</th>
                            <th className="px-3 py-2 text-right">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-amber-100">
                          {backorderLines.map((l, i) => (
                            <tr key={i} className="hover:bg-amber-50/50">
                              <td className="px-3 py-2 font-medium text-slate-800">{l.product_name}</td>
                              <td className="px-3 py-2 text-right font-bold text-amber-800">{l.qty}</td>
                              <td className="px-3 py-2 text-right">
                                <button
                                  type="button"
                                  onClick={() => checkBackorderConsolidation(l.product_id)}
                                  className="text-[11px] font-semibold text-indigo-700 hover:text-indigo-900 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 px-2 py-1 rounded transition-colors"
                                >
                                  ⚡ Check Inbound Consolidation
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Screen 8 Manual Override Form with Dedicated Backorder Column & Real-Time Balance */}
            {overriding && (
              <div className="border border-indigo-200 bg-indigo-50/30 rounded-lg p-4 space-y-4" data-testid="override-form">
                <div>
                  <h4 className="text-xs font-bold text-indigo-900 uppercase tracking-wide">
                    Manual Warehouse Allocation &amp; Backorder Splitting
                  </h4>
                  <p className="text-xs text-slate-600 mt-0.5">
                    Specify exact shipment quantities per warehouse, or allocate to Backorder.
                    Allocations must cover product demand exactly and stay within available warehouse stock.
                  </p>
                </div>

                <div className="overflow-x-auto bg-white border border-slate-200 rounded-lg shadow-2xs">
                  <table className="w-full text-xs text-left">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider">
                        <th className="px-4 py-2.5">Product</th>
                        <th className="px-3 py-2.5 text-center">Demand</th>
                        {warehouses.map((w) => (
                          <th key={w.warehouse} className="px-3 py-2.5 text-center">
                            <div>{w.warehouse}</div>
                            <span className="text-[10px] text-slate-400 font-normal lowercase">avail</span>
                          </th>
                        ))}
                        <th className="px-3 py-2.5 text-center bg-amber-50 text-amber-900 border-l border-amber-200">
                          Backorder
                        </th>
                        <th className="px-4 py-2.5 text-center">Allocation Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {uniqueProductIds.map((pid) => {
                        const pName = fulfillment.lines.find((l) => l.product_id === pid)?.product_name ?? `Product #${pid}`;
                        const demand = fulfillment.lines
                          .filter((l) => l.product_id === pid)
                          .reduce((sum, l) => sum + l.qty, 0);

                        // Calculate current allocated sum for this product
                        const whAllocSum = warehouses.reduce((sum, w) => {
                          const val = Number(split[`${pid}|${w.warehouse}`] ?? 0);
                          return sum + (isNaN(val) ? 0 : val);
                        }, 0);
                        const boVal = Number(split[`${pid}|backorder`] ?? 0);
                        const totalAlloc = whAllocSum + (isNaN(boVal) ? 0 : boVal);
                        const isBalanced = totalAlloc === demand;

                        return (
                          <tr key={pid} className="hover:bg-slate-50/60">
                            <td className="px-4 py-3 font-semibold text-slate-800">
                              {pName}
                            </td>
                            <td className="px-3 py-3 text-center font-bold text-slate-900">
                              {demand}
                            </td>
                            {warehouses.map((w) => {
                              const avail = stock.find((s) => s.warehouse === w.warehouse && s.product_id === pid)?.qty_available ?? 0;
                              const val = split[`${pid}|${w.warehouse}`] ?? "";
                              const numVal = Number(val || 0);
                              const exceedsStock = numVal > avail;

                              return (
                                <td key={w.warehouse} className="px-3 py-3 text-center">
                                  <input
                                    type="number"
                                    min={0}
                                    value={val}
                                    data-testid={`split-${pid}-${w.warehouse}`}
                                    onChange={(e) =>
                                      setSplit({ ...split, [`${pid}|${w.warehouse}`]: e.target.value })
                                    }
                                    placeholder="0"
                                    className={`border rounded px-2 py-1 w-16 text-center text-xs font-semibold ${
                                      exceedsStock
                                        ? "border-red-400 bg-red-50 text-red-800"
                                        : "border-slate-300 bg-white text-slate-900"
                                    }`}
                                  />
                                  <span className={`block text-[10px] mt-0.5 ${exceedsStock ? "text-red-600 font-bold" : "text-slate-400"}`}>
                                    max: {avail}
                                  </span>
                                </td>
                              );
                            })}
                            {/* Dedicated Backorder Column */}
                            <td className="px-3 py-3 text-center bg-amber-50/50 border-l border-amber-200">
                              <input
                                type="number"
                                min={0}
                                value={split[`${pid}|backorder`] ?? ""}
                                data-testid={`split-${pid}-backorder`}
                                onChange={(e) =>
                                  setSplit({ ...split, [`${pid}|backorder`]: e.target.value })
                                }
                                placeholder="0"
                                className="border border-amber-300 rounded px-2 py-1 w-16 text-center text-xs font-bold text-amber-900 bg-white"
                              />
                              <span className="block text-[10px] mt-0.5 text-amber-700">backorder</span>
                            </td>
                            {/* Real-Time Balance Counter */}
                            <td className="px-4 py-3 text-center">
                              {isBalanced ? (
                                <span className="inline-flex items-center px-2.5 py-1 rounded text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                                  ✓ Balanced ({totalAlloc}/{demand})
                                </span>
                              ) : totalAlloc < demand ? (
                                <span className="inline-flex items-center px-2 py-1 rounded text-xs font-semibold bg-red-100 text-red-800 border border-red-200">
                                  Short by {demand - totalAlloc}
                                </span>
                              ) : (
                                <span className="inline-flex items-center px-2 py-1 rounded text-xs font-semibold bg-red-100 text-red-800 border border-red-200">
                                  Over by {totalAlloc - demand}
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="flex items-center gap-3 pt-2">
                  <button
                    onClick={applyOverride}
                    data-testid="apply-override"
                    className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-md px-4 py-2 text-xs shadow-sm transition-all"
                  >
                    Apply Override &amp; Recalculate Split
                  </button>
                  <button
                    onClick={() => toggleOverride()}
                    className="text-xs text-slate-600 hover:text-slate-800 border border-slate-300 rounded-md px-3 py-2 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </section>
        );
      })()}

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
