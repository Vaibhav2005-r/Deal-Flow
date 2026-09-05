import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type PortalLine, type PortalMessage, type PortalQuoteDetail } from "@/lib/api";

export default function QuoteDetail() {
  const { id } = useParams<{ id: string }>();

  const [quote, setQuote] = useState<PortalQuoteDetail | null>(null);
  const [messages, setMessages] = useState<PortalMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Active top navigation tab: 'quotation' | 'messages' | 'profile'
  // tabs are now the portal shell's; this screen only renders the quotation
  const [activeTab] = useState<"quotation" | "messages" | "profile">("quotation");

  // Negotiation Form state (Screen 11 wireframe)
  const [lineComments, setLineComments] = useState<Record<number, string>>({});
  const [counterDiscount, setCounterDiscount] = useState<string>("");
  const [deliveryDate, setDeliveryDate] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [confirming, setConfirming] = useState(false);

  // Separate message thread quick reply
  const [quickReply, setQuickReply] = useState("");

  const user = (() => {
    try {
      const raw = localStorage.getItem("df360.portal.user");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  })();

  async function loadData() {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const [qData, mData] = await Promise.all([
        api.get<PortalQuoteDetail>(`/api/portal/quotes/${id}`, "portal"),
        api.get<PortalMessage[]>(`/api/portal/quotes/${id}/messages`, "portal"),
      ]);
      setQuote(qData);
      setMessages(mData);

      // Prepopulate line comments if previous messages targeted lines
      const initialComments: Record<number, string> = {};
      mData.forEach((m) => {
        if (m.quote_line_id) {
          initialComments[m.quote_line_id] = m.body;
        }
      });
      setLineComments(initialComments);

      // Prepopulate counter discount from latest counter offer if present
      const latestCounter = [...mData].reverse().find((m) => m.counter_discount_pct !== null);
      if (latestCounter?.counter_discount_pct) {
        setCounterDiscount(latestCounter.counter_discount_pct);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load quotation details");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [id]);

  function formatCurrency(val: string | number) {
    const n = Number(val);
    return isNaN(n)
      ? String(val)
      : `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  /**
   * Submit Negotiation Request (Screen 11 `[ Submit Request ]` button).
   * Bundles per-line customer comments, requested delivery date, and counter discount %,
   * records the portal message(s), and triggers CUSTOMER_COUNTER transition.
   */
  async function handleSubmitRequest(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!id || !quote) return;

    const discountVal = counterDiscount.trim();
    const dateVal = deliveryDate.trim();
    const hasLineComments = Object.values(lineComments).some((c) => c.trim().length > 0);

    if (!discountVal && !hasLineComments && !dateVal) {
      setError("Please provide a counter discount %, requested delivery date, or a line comment.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      // 1. Post messages for any per-line comments
      const commentedLineIds = Object.entries(lineComments).filter(([, comment]) => comment.trim().length > 0);
      
      if (commentedLineIds.length > 0) {
        for (const [lineIdStr, comment] of commentedLineIds) {
          const lineId = Number(lineIdStr);
          await api.post(
            `/api/portal/quotes/${id}/messages`,
            {
              body: dateVal ? `[Delivery: ${dateVal}] ${comment.trim()}` : comment.trim(),
              quote_line_id: lineId,
              counter_discount_pct: discountVal ? discountVal : null,
            },
            "portal"
          );
        }
      } else {
        // General negotiation request
        const bodyText = [
          discountVal ? `Customer proposed ${discountVal}% counter discount.` : "",
          dateVal ? `Requested Delivery Date: ${dateVal}.` : "",
        ].filter(Boolean).join(" ");

        await api.post(
          `/api/portal/quotes/${id}/messages`,
          {
            body: bodyText || "Customer submitted negotiation request.",
            counter_discount_pct: discountVal ? discountVal : null,
          },
          "portal"
        );
      }

      // 2. Formalize counter transition (SENT -> UNDER_NEGOTIATION)
      if (discountVal || quote.state === "SENT") {
        await api.post(`/api/portal/quotes/${id}/counter`, {}, "portal");
      }

      setSuccess("Your negotiation request has been submitted! Quotation is now under active negotiation.");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit negotiation request");
    } finally {
      setSubmitting(false);
    }
  }

  /**
   * Confirm Quotation (Screen 11 `[ Confirm Quotation ]` button).
   */
  async function handleConfirmQuote() {
    if (!id) return;
    if (!window.confirm("Are you sure you want to accept and confirm this quotation?")) {
      return;
    }
    setConfirming(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await api.post<{ quotation_id: number; state: string }>(
        `/api/portal/quotes/${id}/confirm`,
        {},
        "portal"
      );
      setSuccess("Quotation successfully confirmed! Your order is being routed to fulfillment.");
      setQuote((prev) => (prev ? { ...prev, state: res.state } : null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to confirm quotation");
    } finally {
      setConfirming(false);
    }
  }

  async function handleSendQuickReply(e: React.FormEvent) {
    e.preventDefault();
    if (!id || !quickReply.trim()) return;
    try {
      await api.post(
        `/api/portal/quotes/${id}/messages`,
        { body: quickReply.trim() },
        "portal"
      );
      setQuickReply("");
      const mData = await api.get<PortalMessage[]>(`/api/portal/quotes/${id}/messages`, "portal");
      setMessages(mData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send reply");
    }
  }

  const isActionable = quote?.state === "SENT" || quote?.state === "UNDER_NEGOTIATION";

  return (
    <div className="min-h-screen bg-[#0f172a] text-slate-100 font-sans">
      {/* Top Navigation Bar with DealFlow360 and Tabs matching Wireframe */}
      {/* chrome lives in PortalShell — one header, one place */}

      <main className="max-w-6xl mx-auto px-6 py-8">
        {error && (
          <div className="p-4 mb-6 bg-red-950/80 border border-red-500/50 rounded-xl text-sm text-red-200 flex items-center justify-between">
            <span>⚠️ {error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-white text-xs">✕</button>
          </div>
        )}

        {success && (
          <div className="p-4 mb-6 bg-emerald-950/80 border border-emerald-500/50 rounded-xl text-sm text-emerald-200 flex items-center justify-between">
            <span>✓ {success}</span>
            <button onClick={() => setSuccess(null)} className="text-emerald-400 hover:text-white text-xs">✕</button>
          </div>
        )}

        {loading || !quote ? (
          <div className="bg-[#1e293b] border border-slate-700 rounded-2xl p-16 text-center text-slate-400 text-sm">
            <div className="inline-block animate-spin text-2xl mb-2">⏳</div>
            <p>Loading quotation #Q-{id}…</p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* TAB: PROFILE */}
            {activeTab === "profile" && (
              <div className="bg-[#1e293b] border border-slate-700 rounded-2xl p-6 shadow-xl space-y-4">
                <h3 className="text-lg font-bold text-white border-b border-slate-700 pb-3">Customer Account Profile</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-xs text-slate-400 block uppercase font-medium">Company / Client</span>
                    <span className="font-semibold text-slate-200">{quote.customer_name}</span>
                  </div>
                  <div>
                    <span className="text-xs text-slate-400 block uppercase font-medium">Logged-In Contact</span>
                    <span className="font-semibold text-slate-200">{user?.full_name || "Authorized Buyer"}</span>
                  </div>
                  <div>
                    <span className="text-xs text-slate-400 block uppercase font-medium">Portal Role</span>
                    <span className="font-semibold text-slate-200">Customer Authorized Representative</span>
                  </div>
                  <div>
                    <span className="text-xs text-slate-400 block uppercase font-medium">Account Status</span>
                    <span className="font-semibold text-emerald-400">Active · Direct Commercial Portal</span>
                  </div>
                </div>
              </div>
            )}

            {/* TAB: MESSAGES */}
            {activeTab === "messages" && (
              <div className="bg-[#1e293b] border border-slate-700 rounded-2xl p-6 shadow-xl flex flex-col h-[600px]">
                <div className="border-b border-slate-700 pb-3 mb-4 flex items-center justify-between">
                  <div>
                    <h3 className="text-base font-bold text-white">Quotation Discussion &amp; Negotiation History</h3>
                    <p className="text-xs text-slate-400">Direct message exchange with your DealFlow360 sales representative.</p>
                  </div>
                  <span className="text-xs font-mono bg-slate-800 text-slate-300 px-2.5 py-1 rounded">
                    Quote #Q-{quote.id} · v{quote.version}
                  </span>
                </div>

                <div className="flex-1 overflow-y-auto space-y-3 pr-2">
                  {messages.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-slate-500 text-sm">
                      <p>No messages exchanged yet.</p>
                    </div>
                  ) : (
                    messages.map((m) => (
                      <div
                        key={m.id}
                        className={`p-4 rounded-xl border text-sm ${
                          m.counter_discount_pct !== null
                            ? "bg-amber-950/40 border-amber-500/50"
                            : "bg-slate-800/80 border-slate-700"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="font-bold text-xs text-slate-200">{m.author_name}</span>
                          <span className="text-[11px] text-slate-400 font-mono">
                            {m.created_at.slice(0, 19).replace("T", " ")}
                          </span>
                        </div>
                        {m.counter_discount_pct !== null && (
                          <div className="mb-2 inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded bg-amber-500/20 text-amber-300 text-xs font-semibold border border-amber-500/40">
                            🏷️ Counter Discount: {m.counter_discount_pct}%
                            {m.quote_line_id ? ` on line #${m.quote_line_id}` : ""}
                          </div>
                        )}
                        <p className="text-slate-300 text-xs whitespace-pre-wrap leading-relaxed">{m.body}</p>
                      </div>
                    ))
                  )}
                </div>

                {isActionable && (
                  <form onSubmit={handleSendQuickReply} className="mt-4 pt-4 border-t border-slate-700 flex gap-2">
                    <input
                      type="text"
                      value={quickReply}
                      onChange={(e) => setQuickReply(e.target.value)}
                      placeholder="Type a message to your sales rep…"
                      className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                    />
                    <button
                      type="submit"
                      disabled={!quickReply.trim()}
                      className="bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
                    >
                      Send Reply
                    </button>
                  </form>
                )}
              </div>
            )}

            {/* TAB: MY QUOTATION (SCREEN 11 NEGOTIATION SCREEN) */}
            {activeTab === "quotation" && (
              <div className="space-y-6">
                {/* Main Screen 11 Container matching Mockup */}
                <div className="bg-[#111827] border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-2xl space-y-6">
                  {/* Title & Subtitle */}
                  <div>
                    <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                      Customer Portal Negotiation Screen
                    </h2>
                    <p className="text-sm text-slate-400 mt-1 font-normal">
                      Customer reviews and negotiates the quote directly, no email needed
                    </p>
                  </div>

                  {/* Status Banner */}
                  <div className="flex items-center">
                    <div
                      className={`inline-flex items-center px-4 py-1.5 rounded-lg text-xs font-bold border tracking-wide uppercase ${
                        quote.state === "UNDER_NEGOTIATION"
                          ? "bg-[#b45309] text-white border-amber-400 shadow-md"
                          : quote.state === "SENT"
                          ? "bg-blue-900/80 text-blue-100 border-blue-400"
                          : quote.state === "CONFIRMED"
                          ? "bg-emerald-800 text-emerald-100 border-emerald-400"
                          : "bg-slate-800 text-slate-300 border-slate-600"
                      }`}
                    >
                      Status: {quote.state === "UNDER_NEGOTIATION" ? "Under Negotiation" : quote.state === "SENT" ? "Awaiting Your Review" : quote.state}
                    </div>
                  </div>

                  {/* Per-Line Negotiation Table */}
                  <div className="border border-slate-700/80 rounded-xl overflow-hidden bg-[#182234]">
                    <table className="w-full text-left text-sm border-collapse">
                      <thead>
                        <tr className="border-b border-slate-700/80 text-xs font-semibold text-slate-300 uppercase tracking-wider bg-slate-900/50">
                          <th className="px-6 py-4 w-1/3">Line</th>
                          <th className="px-6 py-4 w-2/3">Customer Comment</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-700/60">
                        {quote.lines.map((ln: PortalLine) => (
                          <tr key={ln.id} className="hover:bg-slate-800/40 transition-colors">
                            <td className="px-6 py-4 align-top">
                              <p className="font-bold text-white text-sm">{ln.product_name}</p>
                              <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-slate-400">
                                <span>Qty: <strong className="text-slate-200">{ln.qty}</strong></span>
                                <span>·</span>
                                <span>Unit: <strong className="text-slate-200">{formatCurrency(ln.unit_price)}</strong></span>
                                <span>·</span>
                                <span className="text-blue-400">Offered Disc: {Number(ln.discount_pct).toFixed(1)}%</span>
                                <span>·</span>
                                <span className="font-semibold text-white">Net: {formatCurrency(ln.net_value)}</span>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              {isActionable ? (
                                <input
                                  type="text"
                                  value={lineComments[ln.id] ?? ""}
                                  onChange={(e) =>
                                    setLineComments((prev) => ({
                                      ...prev,
                                      [ln.id]: e.target.value,
                                    }))
                                  }
                                  placeholder={
                                    ln.product_name.toLowerCase().includes("warranty")
                                      ? "e.g. Can this be 15% off instead of 10%?"
                                      : "e.g. Can we push this to next month?"
                                  }
                                  className="w-full bg-[#0f172a] border border-slate-600/80 rounded-lg px-3.5 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                                />
                              ) : (
                                <span className="text-xs text-slate-400 italic">
                                  {lineComments[ln.id] || "No customer comment recorded."}
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Commercial Terms Form: Counter Discount % & Requested Delivery Date */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1.5 tracking-wide">
                        Counter Discount %
                      </label>
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="0.5"
                        disabled={!isActionable}
                        value={counterDiscount}
                        onChange={(e) => setCounterDiscount(e.target.value)}
                        placeholder="e.g. 15"
                        className="w-full bg-[#1e293b] border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1.5 tracking-wide">
                        Requested Delivery Date
                      </label>
                      <input
                        type="date"
                        disabled={!isActionable}
                        value={deliveryDate}
                        onChange={(e) => setDeliveryDate(e.target.value)}
                        className="w-full bg-[#1e293b] border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
                      />
                    </div>
                  </div>

                  {/* Action Buttons: [ Submit Request ] & [ Confirm Quotation ] */}
                  {isActionable && (
                    <div className="flex flex-wrap items-center gap-4 pt-2">
                      <button
                        type="button"
                        onClick={() => handleSubmitRequest()}
                        disabled={submitting}
                        className="bg-slate-800 hover:bg-slate-700 text-white font-bold px-6 py-2.5 rounded-lg text-xs tracking-wide border border-slate-600 transition-all shadow-md disabled:opacity-50 cursor-pointer"
                      >
                        {submitting ? "Submitting Request…" : "Submit Request"}
                      </button>

                      <button
                        type="button"
                        onClick={handleConfirmQuote}
                        disabled={confirming}
                        className="bg-[#22c55e] hover:bg-[#16a34a] text-slate-950 font-extrabold px-6 py-2.5 rounded-lg text-xs tracking-wide transition-all shadow-lg hover:shadow-emerald-500/20 disabled:opacity-50 cursor-pointer"
                      >
                        {confirming ? "Confirming…" : "Confirm Quotation"}
                      </button>
                    </div>
                  )}

                  {/* Footnote Notice Box from Wireframe */}
                  <div className="p-4 rounded-xl border border-amber-600/60 bg-[#1c1917]/70 text-amber-200/90 text-xs leading-relaxed">
                    If final terms exceed thresholds, the quote automatically re-enters approval (Screen 6).
                  </div>
                </div>

                {/* Quotation Commercial Total & Summary Card */}
                <div className="bg-[#1e293b] border border-slate-700 rounded-2xl p-6 shadow-xl flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h3 className="text-base font-bold text-white">Commercial Proposal Summary</h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Proposal Version: <span className="font-mono text-slate-200">v{quote.version}</span> ·
                      Total Items: <span className="font-semibold text-slate-200">{quote.lines.length}</span>
                    </p>
                  </div>

                  <div className="text-right">
                    <span className="text-xs uppercase text-slate-400 tracking-wider block font-semibold">Total Net Value</span>
                    <span className="text-2xl sm:text-3xl font-black text-white">{formatCurrency(quote.net_total)}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
