import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type PortalLine, type PortalMessage, type PortalQuoteDetail } from "@/lib/api";
import { clearToken } from "@/lib/auth";

export default function QuoteDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [quote, setQuote] = useState<PortalQuoteDetail | null>(null);
  const [messages, setMessages] = useState<PortalMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // New message / counter form state
  const [msgBody, setMsgBody] = useState("");
  const [selectedLineId, setSelectedLineId] = useState<string>("");
  const [counterDiscount, setCounterDiscount] = useState<string>("");
  const [submittingMsg, setSubmittingMsg] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);

  const user = (() => {
    try {
      const raw = localStorage.getItem("df360.portal.user");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  })();

  function handleLogout() {
    clearToken("portal");
    localStorage.removeItem("df360.portal.user");
    navigate("/portal/login", { replace: true });
  }

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

  async function handleSendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!id || !msgBody.trim()) return;

    setSubmittingMsg(true);
    setError(null);
    setSuccess(null);

    const payload: {
      body: string;
      quote_line_id?: number | null;
      counter_discount_pct?: string | null;
    } = {
      body: msgBody.trim(),
    };

    if (selectedLineId) {
      payload.quote_line_id = Number(selectedLineId);
    }
    if (counterDiscount.trim()) {
      payload.counter_discount_pct = counterDiscount.trim();
    }

    try {
      await api.post(`/api/portal/quotes/${id}/messages`, payload, "portal");
      setMsgBody("");
      setSelectedLineId("");
      setCounterDiscount("");
      setSuccess("Message posted to discussion thread.");
      // Refresh messages
      const mData = await api.get<PortalMessage[]>(`/api/portal/quotes/${id}/messages`, "portal");
      setMessages(mData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to post message");
    } finally {
      setSubmittingMsg(false);
    }
  }

  async function handleSubmitCounter() {
    if (!id) return;
    setActionBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await api.post<{ quotation_id: number; state: string }>(
        `/api/portal/quotes/${id}/counter`,
        {},
        "portal",
      );
      setSuccess("Counter-proposal formally submitted. Quotation is now under negotiation.");
      setQuote((prev) => (prev ? { ...prev, state: res.state } : null));
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit counter-proposal");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleConfirmQuote() {
    if (!id) return;
    if (!window.confirm("Are you sure you want to accept and confirm this quotation?")) {
      return;
    }
    setActionBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await api.post<{ quotation_id: number; state: string }>(
        `/api/portal/quotes/${id}/confirm`,
        {},
        "portal",
      );
      setSuccess("Quotation successfully confirmed! Order is being routed to fulfillment.");
      setQuote((prev) => (prev ? { ...prev, state: res.state } : null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to confirm quotation");
    } finally {
      setActionBusy(false);
    }
  }

  const hasCounterDiscounts = messages.some((m) => m.counter_discount_pct !== null);
  const isActionable = quote?.state === "SENT" || quote?.state === "UNDER_NEGOTIATION";

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-6 py-4 shadow-sm">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              to="/portal"
              className="text-xs font-semibold text-slate-500 hover:text-slate-900 flex items-center gap-1 mr-2"
            >
              ← All Quotes
            </Link>
            <div className="h-5 w-px bg-slate-200 mr-2" />
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-sm">
              DF
            </div>
            <div>
              <h1 className="text-sm font-bold text-slate-900 leading-tight">DealFlow360</h1>
              <p className="text-xs text-indigo-600 font-medium">Customer Portal</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-xs font-semibold text-slate-800">
                {user?.full_name ?? quote?.customer_name ?? "Customer Contact"}
              </p>
              <p className="text-xs text-slate-500">{quote?.customer_name}</p>
            </div>
            <button
              onClick={handleLogout}
              className="text-xs text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-md font-medium transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {error && (
          <div className="p-4 mb-6 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {error}
          </div>
        )}

        {success && (
          <div className="p-4 mb-6 bg-emerald-50 border border-emerald-200 rounded-lg text-sm text-emerald-800">
            {success}
          </div>
        )}

        {loading || !quote ? (
          <div className="bg-white border border-slate-200 rounded-xl p-12 text-center text-slate-500 text-sm">
            Loading quotation #Q-{id}…
          </div>
        ) : (
          <div className="space-y-6">
            {/* Header summary banner */}
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-2xl font-extrabold text-slate-900">
                    Quotation #Q-{quote.id}
                  </h2>
                  <span
                    className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${
                      quote.state === "SENT"
                        ? "bg-blue-100 text-blue-800 border border-blue-200"
                        : quote.state === "UNDER_NEGOTIATION"
                        ? "bg-amber-100 text-amber-800 border border-amber-200"
                        : quote.state === "CONFIRMED"
                        ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                        : "bg-slate-100 text-slate-800 border border-slate-200"
                    }`}
                  >
                    {quote.state === "SENT"
                      ? "Awaiting Your Review"
                      : quote.state === "UNDER_NEGOTIATION"
                      ? "Under Active Negotiation"
                      : quote.state === "CONFIRMED"
                      ? "Confirmed & Accepted"
                      : quote.state}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Customer: <span className="font-semibold text-slate-700">{quote.customer_name}</span> ·
                  Revision Version: <span className="font-mono text-slate-700">v{quote.version}</span>
                </p>
              </div>

              <div className="text-right">
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Total Commercial Proposal
                </p>
                <p className="text-3xl font-extrabold text-slate-900">
                  {formatCurrency(quote.net_total)}
                </p>
              </div>
            </div>

            {/* Commercial Lines Table */}
            <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-slate-900">Proposed Line Items</h3>
                  <p className="text-xs text-slate-500">Commercial terms offered by your sales representative.</p>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    <tr>
                      <th className="px-6 py-3.5">Product & SKU</th>
                      <th className="px-6 py-3.5 text-center">Category</th>
                      <th className="px-6 py-3.5 text-center">Qty</th>
                      <th className="px-6 py-3.5 text-right">Unit Price</th>
                      <th className="px-6 py-3.5 text-right">Offered Discount</th>
                      <th className="px-6 py-3.5 text-right">Net Value</th>
                      {isActionable && <th className="px-6 py-3.5 text-center">Counter</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {quote.lines.map((ln: PortalLine) => (
                      <tr key={ln.id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-6 py-4">
                          <p className="font-semibold text-slate-900">{ln.product_name}</p>
                          <p className="text-xs text-slate-400 font-mono">Line #{ln.id}</p>
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
                            {ln.category}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center font-medium text-slate-800">
                          {ln.qty}
                        </td>
                        <td className="px-6 py-4 text-right text-slate-700">
                          {formatCurrency(ln.unit_price)}
                        </td>
                        <td className="px-6 py-4 text-right font-medium text-indigo-700">
                          {Number(ln.discount_pct).toFixed(1)}%
                        </td>
                        <td className="px-6 py-4 text-right font-semibold text-slate-900">
                          {formatCurrency(ln.net_value)}
                        </td>
                        {isActionable && (
                          <td className="px-6 py-4 text-center">
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedLineId(String(ln.id));
                                setCounterDiscount(String(Math.min(100, Math.round(Number(ln.discount_pct) + 5))));
                              }}
                              className="text-xs font-medium text-indigo-600 hover:text-indigo-800 bg-indigo-50 hover:bg-indigo-100 px-2.5 py-1 rounded transition-colors"
                            >
                              Counter
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="bg-slate-50 border-t border-slate-200">
                    <tr>
                      <td colSpan={5} className="px-6 py-3 text-right font-semibold text-slate-700">
                        Total Net:
                      </td>
                      <td className="px-6 py-3 text-right font-bold text-slate-900">
                        {formatCurrency(quote.net_total)}
                      </td>
                      {isActionable && <td />}
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>

            {/* Negotiation & Messaging Section */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Message Thread */}
              <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col h-[520px]">
                <div className="border-b border-slate-100 pb-3 mb-4">
                  <h3 className="text-base font-bold text-slate-900">Negotiation Thread</h3>
                  <p className="text-xs text-slate-500">History of comments and counter proposals.</p>
                </div>

                <div className="flex-1 overflow-y-auto space-y-4 pr-1">
                  {messages.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 text-xs">
                      <p>No messages or counter-offers yet.</p>
                      <p className="mt-1">Post a message below to negotiate pricing.</p>
                    </div>
                  ) : (
                    messages.map((m) => (
                      <div
                        key={m.id}
                        className={`p-4 rounded-xl text-sm border ${
                          m.counter_discount_pct !== null
                            ? "bg-amber-50/70 border-amber-200"
                            : "bg-slate-50 border-slate-200"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="font-semibold text-xs text-slate-900">
                            {m.author_name}
                          </span>
                          <span className="text-[11px] text-slate-400 font-mono">
                            {m.created_at.slice(0, 19).replace("T", " ")}
                          </span>
                        </div>

                        {m.counter_discount_pct !== null && (
                          <div className="mb-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-100 text-amber-900 text-xs font-semibold border border-amber-300">
                            <span>🏷️ Counter Proposal:</span>
                            <span>
                              {m.counter_discount_pct}% discount
                              {m.quote_line_id ? ` on Line #${m.quote_line_id}` : ""}
                            </span>
                          </div>
                        )}

                        <p className="text-slate-700 whitespace-pre-wrap text-xs leading-relaxed">
                          {m.body}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Action and Comment Input Box */}
              <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col justify-between">
                <div>
                  <div className="border-b border-slate-100 pb-3 mb-4">
                    <h3 className="text-base font-bold text-slate-900">Propose Counter or Comment</h3>
                    <p className="text-xs text-slate-500">
                      Add a comment or propose a modified discount on any line.
                    </p>
                  </div>

                  {isActionable ? (
                    <form onSubmit={handleSendMessage} className="space-y-4">
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">
                          Comment / Note to Sales Rep
                        </label>
                        <textarea
                          rows={3}
                          required
                          value={msgBody}
                          onChange={(e) => setMsgBody(e.target.value)}
                          placeholder="e.g. We would like to proceed if we can achieve an additional 5% discount on the hardware..."
                          className="w-full border border-slate-300 rounded-lg p-2.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-semibold text-slate-700 mb-1">
                            Target Line (Optional)
                          </label>
                          <select
                            value={selectedLineId}
                            onChange={(e) => setSelectedLineId(e.target.value)}
                            className="w-full border border-slate-300 rounded-lg p-2 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          >
                            <option value="">General (No Line)</option>
                            {quote.lines.map((ln) => (
                              <option key={ln.id} value={ln.id}>
                                Line #{ln.id} — {ln.product_name.slice(0, 22)}… ({ln.discount_pct}%)
                              </option>
                            ))}
                          </select>
                        </div>

                        <div>
                          <label className="block text-xs font-semibold text-slate-700 mb-1">
                            Counter Discount % (Optional)
                          </label>
                          <input
                            type="number"
                            min="0"
                            max="100"
                            step="0.5"
                            value={counterDiscount}
                            onChange={(e) => setCounterDiscount(e.target.value)}
                            placeholder="e.g. 18.0"
                            className="w-full border border-slate-300 rounded-lg p-2 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          />
                        </div>
                      </div>

                      <button
                        type="submit"
                        disabled={submittingMsg || !msgBody.trim()}
                        className="w-full bg-slate-900 hover:bg-slate-800 text-white rounded-lg px-4 py-2 text-xs font-semibold transition-colors disabled:opacity-50"
                      >
                        {submittingMsg ? "Posting message…" : "Post Comment / Proposal to Thread"}
                      </button>
                    </form>
                  ) : (
                    <div className="p-6 bg-slate-50 border border-slate-200 rounded-lg text-center text-xs text-slate-500">
                      Negotiations for this quotation are closed (status: {quote.state}).
                    </div>
                  )}
                </div>

                {/* Final Decision Buttons */}
                {isActionable && (
                  <div className="mt-6 pt-5 border-t border-slate-200 space-y-3">
                    <p className="text-xs font-semibold text-slate-700">Official Quotation Actions</p>

                    <div className="flex flex-col sm:flex-row gap-3">
                      <button
                        type="button"
                        onClick={handleSubmitCounter}
                        disabled={actionBusy || !hasCounterDiscounts || quote.state === "UNDER_NEGOTIATION"}
                        className={`flex-1 rounded-lg px-4 py-2.5 text-xs font-bold transition-all shadow-sm ${
                          quote.state === "UNDER_NEGOTIATION"
                            ? "bg-amber-100 text-amber-800 border border-amber-300 cursor-not-allowed"
                            : hasCounterDiscounts
                            ? "bg-amber-500 hover:bg-amber-600 text-white"
                            : "bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed"
                        }`}
                        title={
                          !hasCounterDiscounts
                            ? "Add at least one counter-discount in the thread before submitting"
                            : ""
                        }
                      >
                        {quote.state === "UNDER_NEGOTIATION"
                          ? "✓ Counter Already Submitted"
                          : "Submit Counter Proposal"}
                      </button>

                      <button
                        type="button"
                        onClick={handleConfirmQuote}
                        disabled={actionBusy}
                        className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg px-4 py-2.5 text-xs font-bold transition-all shadow-sm"
                      >
                        Accept & Confirm Terms
                      </button>
                    </div>

                    {!hasCounterDiscounts && quote.state === "SENT" && (
                      <p className="text-[11px] text-slate-400 italic text-center">
                        Tip: To submit a counter-proposal, first post a message with a counter-discount %.
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
