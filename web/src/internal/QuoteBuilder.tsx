import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  api,
  type Customer,
  type Policy,
  type PortalMessage,
  type Product,
  type Quote,
  type Score,
} from "@/lib/api";
import { ApprovalTrail, LineTable, RiskBadge, StateBadge, currency, SearchableSelect } from "./components";
import UpsellPanel from "./UpsellPanel";
import OfferHistoryLog from "@/components/OfferHistoryLog";
import { getCurrentUser } from "@/lib/auth";

export default function QuoteBuilder() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [score, setScore] = useState<Score | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionNote, setActionNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Negotiation thread state
  const [messages, setMessages] = useState<PortalMessage[]>([]);
  const [replyText, setReplyText] = useState("");
  const [isEditingTerms, setIsEditingTerms] = useState(false);
  const [showCounterModal, setShowCounterModal] = useState(false);
  const [counterDiscount, setCounterDiscount] = useState("");
  const [counterBody, setCounterBody] = useState("");
  const [counterLineId, setCounterLineId] = useState<number | null>(null);

  const [customerId, setCustomerId] = useState<number | null>(null);
  const [productId, setProductId] = useState<number | null>(null);
  const [qty, setQty] = useState(1);
  const [discount, setDiscount] = useState("18");
  const [orderDiscount, setOrderDiscount] = useState<string>("");

  /**
   * Order margin, from the same net and cost figures the engine uses.
   * Null when the quote has no lines yet -- an indicator reading 0% on an
   * empty quote looks like a loss-making deal rather than an absent one.
   */
  const orderMargin: number | null = (() => {
    if (!quote?.lines?.length) return null;
    const net = quote.lines.reduce((n, l) => n + Number(l.net_value), 0);
    if (net <= 0) return null;
    const cost = quote.lines.reduce((n, l) => {
      const m = l.margin_pct === null ? null : Number(l.margin_pct);
      const lineNet = Number(l.net_value);
      return n + (m === null ? 0 : lineNet * (1 - m / 100));
    }, 0);
    return ((net - cost) / net) * 100;
  })();

  async function applyOrderDiscount() {
    if (!quote || orderDiscount === "") return;
    await run(async () => {
      const updated = await api.post<Quote>(
        `/api/quotes/${quote.id}/order-discount`,
        { discount_pct: orderDiscount },
      );
      setQuote(updated);
    });
  }

  useEffect(() => {
    Promise.all([
      api.get<Customer[]>("/api/customers"),
      api.get<Product[]>("/api/products"),
      api.get<Policy[]>("/api/discount-policies"),
    ]).then(([c, p, pol]) => {
      setCustomers(c);
      setProducts(p);
      setPolicies(pol);
      if (!id) {
        setCustomerId(c.find((x) => x.tier === "gold")?.id ?? c[0]?.id ?? null);
      }
      setProductId(p.find((x) => x.sku === "SV-INST-01")?.id ?? p[0]?.id ?? null);
    }).catch((e) => setError(String(e.message)));
  }, [id]);

  const loadMessages = async (quoteId: number) => {
    try {
      const msgs = await api.get<PortalMessage[]>(`/api/quotes/${quoteId}/messages`);
      setMessages(msgs);
    } catch {
      setMessages([]);
    }
  };

  useEffect(() => {
    if (!id) {
      setQuote(null);
      setScore(null);
      setMessages([]);
      return;
    }
    run(async () => {
      const q = await api.get<Quote>(`/api/quotes/${id}`);
      setQuote(q);
      setCustomerId(q.customer_id);
      setScore(null);
      await loadMessages(Number(id));
    });
  }, [id]);

  const customer = customers.find((c) => c.id === customerId);
  const product = products.find((p) => p.id === productId);
  /** Show the ceiling BEFORE the rep breaches it — governance is not a trap. */
  const ceiling = policies.find(
    (p) => p.tier === customer?.tier && p.category === product?.category,
  );
  const willBreach = ceiling && Number(discount) > Number(ceiling.ceiling_pct);

  async function run<T>(fn: () => Promise<T>) {
    setError(null);
    try { return await fn(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  const createQuote = () =>
    run(async () => {
      const q = await api.post<Quote>("/api/quotes", { customer_id: customerId, lines: [] });
      setQuote(q);
      setScore(null);
      navigate(`/quotes/${q.id}`);
    });

  const startNew = () => {
    setQuote(null);
    setScore(null);
    setError(null);
    navigate("/");
  };

  const addLine = () =>
    run(async () => {
      if (!quote || !productId) return;
      const q = await api.post<Quote>(`/api/quotes/${quote.id}/lines`, {
        product_id: productId, qty, discount_pct: discount,
      });
      setQuote(q);
    });

  const removeLine = (lineId: number) =>
    run(async () => {
      if (!quote) return;
      const q = await api.del<Quote>(`/api/quotes/${quote.id}/lines/${lineId}`);
      setQuote(q);
    });

  const updateLine = (lineId: number, update: { qty?: number; discount_pct?: string | number }) =>
    run(async () => {
      if (!quote) return;
      setBusy(true);
      setActionNote(null);
      try {
        const q = await api.patch<Quote>(`/api/quotes/${quote.id}/lines/${lineId}`, {
          qty: update.qty !== undefined ? Number(update.qty) : undefined,
          discount_pct: update.discount_pct !== undefined ? String(update.discount_pct) : undefined,
        });
        setQuote(q);
        setActionNote("Line updated! Quotation automatically re-scored and evaluated against governance ceilings.");
        await loadMessages(quote.id);
      } finally {
        setBusy(false);
      }
    });

  const acceptUpsell = (prodId: number) => {
    const prod = products.find((p) => p.id === prodId);
    const pol = policies.find(
      (p) => p.tier === customer?.tier && p.category === prod?.category,
    );
    const ceilingDisc = pol ? String(pol.ceiling_pct) : "0";
    run(async () => {
      if (!quote) return;
      const q = await api.post<Quote>(`/api/quotes/${quote.id}/lines`, {
        product_id: prodId,
        qty: 1,
        discount_pct: ceilingDisc,
      });
      setQuote(q);
    });
  };

  const confirm = () =>
    run(async () => {
      if (!quote) return;
      const s = await api.post<Score>(`/api/quotes/${quote.id}/confirm`, {});
      setScore(s);
      setQuote(await api.get<Quote>(`/api/quotes/${quote.id}`));
    });

  const acceptCounter = () =>
    run(async () => {
      if (!quote) return;
      setBusy(true);
      setActionNote(null);
      try {
        const res = await api.post<{
          quotation_id: number;
          state: string;
          score: number;
          approval_chain: string[];
          applied_discount_pct: string;
        }>(`/api/quotes/${quote.id}/accept-counter`, {});
        setActionNote(
          `Counter-discount of ${res.applied_discount_pct}% accepted! State is now ${res.state.replaceAll("_", " ")}.`
        );
        const q = await api.get<Quote>(`/api/quotes/${quote.id}`);
        setQuote(q);
        await loadMessages(quote.id);
      } finally {
        setBusy(false);
      }
    });

  const sendToPortal = () =>
    run(async () => {
      if (!quote) return;
      setBusy(true);
      setActionNote(null);
      try {
        await api.post(`/api/quotes/${quote.id}/send-to-portal`, {});
        setActionNote("Quotation successfully delivered to Customer Portal.");
        const q = await api.get<Quote>(`/api/quotes/${quote.id}`);
        setQuote(q);
      } finally {
        setBusy(false);
      }
    });

  const postReply = (e: React.FormEvent) => {
    e.preventDefault();
    if (!quote || !replyText.trim()) return;
    run(async () => {
      setBusy(true);
      try {
        await api.post(`/api/quotes/${quote.id}/messages`, { body: replyText.trim() });
        setReplyText("");
        await loadMessages(quote.id);
      } finally {
        setBusy(false);
      }
    });
  };

  const submitRepCounterOffer = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!quote) return;
    const discVal = counterDiscount.trim() ? parseFloat(counterDiscount) : null;
    const noteText =
      counterBody.trim() ||
      (discVal !== null
        ? `Sales representative offered ${discVal}% revised counter-discount.`
        : "Sales representative delivered revised commercial terms.");

    setBusy(true);
    setActionNote(null);
    try {
      await api.post(`/api/quotes/${quote.id}/counter-offer`, {
        body: noteText,
        counter_discount_pct: discVal,
        quote_line_id: counterLineId,
      });
      setActionNote("Counter-offer delivered directly to customer portal.");
      setShowCounterModal(false);
      setCounterDiscount("");
      setCounterBody("");
      setCounterLineId(null);
      const q = await api.get<Quote>(`/api/quotes/${quote.id}`);
      setQuote(q);
      await loadMessages(quote.id);
    } catch (err: any) {
      setError(err instanceof Error ? err.message : "Failed to deliver counter-offer");
    } finally {
      setBusy(false);
    }
  };

  const lastReturnedStep = quote?.approval_steps
    ?.slice()
    .reverse()
    .find((s) => s.decision === "RETURNED");
  const isRevisionNeeded = quote?.state === "DRAFT" && !!lastReturnedStep;
  const isEditable =
    !quote ||
    quote.state === "DRAFT" ||
    quote.state === "PENDING_MANAGER" ||
    quote.state === "PENDING_FINANCE" ||
    quote.state === "UNDER_NEGOTIATION" ||
    isEditingTerms;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold text-slate-900">
            {quote ? `Quotation #${quote.id}` : "New Quote"}
          </h2>
          {quote && (
            <span className="text-xs px-2 py-0.5 rounded bg-slate-200 text-slate-700 font-medium">
              v{quote.version}
            </span>
          )}
        </div>
        {quote && (
          <div className="flex flex-wrap items-center gap-2">
            {(quote.state === "SENT" || quote.state === "UNDER_NEGOTIATION" || quote.state === "READY_TO_FULFILL") && (
              <div className="flex items-center gap-2 mr-2">
                <button
                  type="button"
                  onClick={() => setShowCounterModal(true)}
                  className="bg-purple-700 hover:bg-purple-800 text-white text-xs font-bold px-3 py-1.5 rounded-lg shadow-xs transition flex items-center gap-1.5 cursor-pointer"
                >
                  <span>💼 Make Counter-Offer</span>
                </button>
                <button
                  type="button"
                  onClick={() => setIsEditingTerms(!isEditingTerms)}
                  className={`${
                    isEditingTerms ? "bg-amber-600 text-white" : "bg-indigo-600 hover:bg-indigo-700 text-white"
                  } text-xs font-bold px-3 py-1.5 rounded-lg shadow-xs transition flex items-center gap-1.5 cursor-pointer`}
                >
                  <span>{isEditingTerms ? "✕ Close Line Editor" : "✏️ Revise Line Items"}</span>
                </button>
              </div>
            )}
            <StateBadge state={quote.state} />
            <RiskBadge score={quote.risk_score ? Number(quote.risk_score) : null} />
          </div>
        )}
      </div>

      {isRevisionNeeded && (
        <div
          className="bg-amber-50 border-l-4 border-amber-500 rounded-r-lg p-4 shadow-sm"
          data-testid="revision-banner"
        >
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-sm font-bold text-amber-900 flex items-center gap-2">
                <span>⚠️ Returned for Revision by {lastReturnedStep.approver_role.replaceAll("_", " ")}</span>
              </h3>
              {lastReturnedStep.reason && (
                <p className="text-sm text-amber-800 mt-1.5 italic bg-amber-100/60 p-2 rounded">
                  "{lastReturnedStep.reason}"
                </p>
              )}
              <p className="text-xs text-amber-700 mt-2 font-medium">
                You can remove lines, add replacement products, or adjust discounts below. Once revised, click <strong>Confirm &amp; score</strong> to re-submit into the approval chain.
              </p>
            </div>
          </div>
        </div>
      )}

      {quote && quote.state !== "DRAFT" && (
        <div className="bg-blue-50 border border-blue-200 text-blue-900 rounded-lg p-3 text-sm flex items-center justify-between">
          <span>
            This quotation is currently <strong>{quote.state.replaceAll("_", " ")}</strong>.
          </span>
          <span className="text-xs text-blue-700 font-medium">
            {quote.state.startsWith("PENDING")
              ? "Awaiting manager/finance review"
              : quote.state === "READY_TO_FULFILL"
              ? "Approved & ready for fulfillment"
              : ""}
          </span>
        </div>
      )}

      {actionNote && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded px-3 py-2 flex items-center justify-between shadow-xs">
          <span>{actionNote}</span>
          <button onClick={() => setActionNote(null)} className="text-emerald-600 hover:text-emerald-900 text-xs font-bold ml-3">✕</button>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-sm rounded px-3 py-2" data-testid="error">
          {error}
        </div>
      )}

      {isEditingTerms && quote && (
        <div className="bg-blue-50 border-2 border-blue-400 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3 shadow-xs">
          <div>
            <h4 className="text-sm font-bold text-blue-950 flex items-center gap-2">
              <span>✏️ Offer Revision Mode Active</span>
            </h4>
            <p className="text-xs text-blue-800 mt-0.5">
              You can modify line quantities, unit prices, and discounts directly in the table below. When done, deliver the revised offer to the customer.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={async () => {
                setIsEditingTerms(false);
                await sendToPortal();
              }}
              disabled={busy}
              className="bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold px-4 py-2 rounded-lg shadow-sm cursor-pointer"
            >
              {busy ? "Delivering…" : "Deliver Revised Offer to Portal →"}
            </button>
            <button
              onClick={() => setIsEditingTerms(false)}
              className="bg-slate-200 hover:bg-slate-300 text-slate-700 text-xs font-semibold px-3 py-2 rounded-lg cursor-pointer"
            >
              Done Editing
            </button>
          </div>
        </div>
      )}

      {quote && (quote.state === "READY_TO_FULFILL" || quote.state === "UNDER_NEGOTIATION" || quote.legal_events?.includes("send_to_portal")) && (
        <div className="bg-gradient-to-r from-emerald-50 to-teal-50 border border-emerald-300 rounded-lg p-4 flex flex-wrap items-center justify-between gap-3 shadow-xs">
          <div>
            <h4 className="text-sm font-bold text-emerald-950 flex items-center gap-2">
              <span>🚀 {quote.state === "UNDER_NEGOTIATION" ? "Deliver Revised Offer to Customer Portal" : "Quotation Approved & Ready for Customer"}</span>
            </h4>
            <p className="text-xs text-emerald-800 mt-0.5">
              {quote.state === "UNDER_NEGOTIATION"
                ? "You can edit line items below, adjust discounts, and deliver your revised offer directly back to the customer's portal."
                : "Deliver this approved quotation to the customer portal so they can review, negotiate, or accept terms."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowCounterModal(true)}
              className="bg-purple-700 hover:bg-purple-800 text-white text-xs font-bold px-3 py-2 rounded-lg shadow-sm cursor-pointer"
            >
              💼 Make Counter-Offer
            </button>
            <button
              onClick={sendToPortal}
              disabled={busy}
              className="bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-bold px-4 py-2 rounded-lg shadow-sm transition disabled:opacity-50 cursor-pointer"
            >
              {busy ? "Sending…" : quote.state === "UNDER_NEGOTIATION" ? "Send Revised Offer to Portal →" : "Send to Customer Portal →"}
            </button>
          </div>
        </div>
      )}

      {/* Offer History & Negotiation Log */}
      {quote && (
        <OfferHistoryLog
          quoteId={quote.id}
          quoteVersion={quote.version}
          quoteState={quote.state}
          lines={quote.lines}
          messages={messages}
          customerName={customers.find((c) => c.id === quote.customer_id)?.name}
          repName={getCurrentUser()?.full_name || "Sales Representative"}
          netTotal={quote.lines?.reduce((sum, l) => sum + (Number(l.qty) * Number(l.unit_price) * (1 - Number(l.discount_pct) / 100)), 0)}
          isInternal={true}
          onMakeCounterOffer={() => setShowCounterModal(true)}
          onReviseTerms={() => setIsEditingTerms(true)}
          onAcceptCounter={(() => {
            const counterMsgs = messages.filter((m) => m.counter_discount_pct !== null);
            return counterMsgs.length > 0 ? acceptCounter : undefined;
          })()}
          latestCustomerCounterPct={(() => {
            const counterMsgs = messages.filter((m) => m.counter_discount_pct !== null);
            return counterMsgs.length > 0 ? Number(counterMsgs[counterMsgs.length - 1].counter_discount_pct) : null;
          })()}
        />
      )}

      {quote && (quote.state === "UNDER_NEGOTIATION" || messages.length > 0) && (
        <section className="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs space-y-3">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Send Quick Note or Clarification to Customer Portal
          </h4>
          <form onSubmit={postReply} className="flex gap-2">
            <input
              type="text"
              placeholder="Post a message or clarification to the customer portal…"
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <button
              type="submit"
              disabled={busy || !replyText.trim()}
              className="bg-slate-900 hover:bg-slate-800 text-white rounded-lg px-4 py-2 text-xs font-semibold transition disabled:opacity-50 cursor-pointer"
            >
              Send Message
            </button>
          </form>
        </section>
      )}

      {/* Sales Representative Counter-Offer Modal */}
      {showCounterModal && quote && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-purple-100 text-purple-700 font-bold text-sm">
                  💼
                </span>
                <div>
                  <h3 className="text-base font-bold text-slate-900">Make Counter-Offer to Customer</h3>
                  <p className="text-xs text-slate-500">Deliver revised pricing or terms to the customer portal.</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowCounterModal(false)}
                className="text-slate-400 hover:text-slate-700 text-sm font-bold cursor-pointer"
              >
                ✕
              </button>
            </div>

            <form onSubmit={submitRepCounterOffer} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Target Proposal Scope
                </label>
                <select
                  value={counterLineId ?? ""}
                  onChange={(e) => setCounterLineId(e.target.value ? Number(e.target.value) : null)}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-xs focus:ring-2 focus:ring-purple-500 focus:outline-none"
                >
                  <option value="">Apply across Entire Quotation (All Lines)</option>
                  {quote.lines.map((l) => (
                    <option key={l.id} value={l.id}>
                      Line: {l.product_name} (Current: {Number(l.discount_pct).toFixed(1)}% off)
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Proposed Counter Discount %
                </label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.5"
                  required
                  value={counterDiscount}
                  onChange={(e) => setCounterDiscount(e.target.value)}
                  placeholder="e.g. 12.5"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-xs focus:ring-2 focus:ring-purple-500 focus:outline-none"
                />
                <span className="text-[11px] text-slate-500 mt-1 block">
                  This will update line discounts and automatically verify governance ceilings.
                </span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Counter-Offer Note / Terms Explanation
                </label>
                <textarea
                  rows={3}
                  value={counterBody}
                  onChange={(e) => setCounterBody(e.target.value)}
                  placeholder="e.g. We can offer 12.5% discount if the order is confirmed by Friday with standard annual SLA."
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-xs focus:ring-2 focus:ring-purple-500 focus:outline-none resize-none"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowCounterModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={busy || !counterDiscount}
                  className="bg-purple-700 hover:bg-purple-800 text-white text-xs font-bold px-4 py-2 rounded-lg shadow-sm transition disabled:opacity-50 cursor-pointer"
                >
                  {busy ? "Delivering Counter…" : "Deliver Counter-Offer to Customer Portal →"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <section className="bg-white border border-slate-200 rounded-lg p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="block text-slate-600 mb-1">Customer</span>
            <SearchableSelect
              dataTestId="customer"
              containerClassName="min-w-64"
              className="min-w-64"
              value={customerId ?? ""}
              onChange={(val) => setCustomerId(Number(val))}
              disabled={!!quote}
              placeholder="Select customer..."
              searchPlaceholder="Search customer by name or tier..."
              options={customers.map((c) => ({
                value: c.id,
                label: c.name,
                sublabel: c.tier,
              }))}
            />
          </label>
          <button
            onClick={quote ? startNew : createQuote}
            data-testid="new-quote"
            className="bg-slate-900 text-white rounded px-3 py-1.5 text-sm font-medium hover:bg-slate-800 transition"
          >
            {quote ? "Start another" : "Create quote"}
          </button>
          <button
            type="button"
            onClick={() => navigate("/quotes")}
            className="text-sm text-slate-500 hover:text-slate-900 underline ml-auto"
          >
            ← View all quotes
          </button>
        </div>
      </section>

      {quote && isEditable && (
        <section className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-700">Add a line</h3>
            {quote.state !== "DRAFT" && (
              <span className="text-xs text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                ⚡ Editing lines mid-flight voids pending approval steps and immediately re-scores.
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="block text-slate-600 mb-1">Product</span>
              <SearchableSelect
                dataTestId="product"
                containerClassName="min-w-72"
                className="min-w-72"
                value={productId ?? ""}
                onChange={(val) => setProductId(Number(val))}
                placeholder="Select a product..."
                searchPlaceholder="Search product by name or category..."
                options={products.map((p) => ({
                  value: p.id,
                  label: p.name,
                  sublabel: `${p.category} · ₹${p.list_price}`,
                }))}
              />
            </label>
            <label className="text-sm">
              <span className="block text-slate-600 mb-1">Qty</span>
              <input
                data-testid="qty" type="number" min={1} value={qty}
                onChange={(e) => setQty(Number(e.target.value))}
                className="border border-slate-300 rounded px-2 py-1.5 text-sm w-20"
              />
            </label>
            <label className="text-sm">
              <span className="block text-slate-600 mb-1">Discount %</span>
              <input
                data-testid="discount" type="number" min={0} max={100} step="0.5" value={discount}
                onChange={(e) => setDiscount(e.target.value)}
                className="border border-slate-300 rounded px-2 py-1.5 text-sm w-24"
              />
            </label>
            <button
              onClick={addLine}
              data-testid="add-line"
              className="bg-slate-700 text-white rounded px-3 py-1.5 text-sm font-medium hover:bg-slate-600 transition"
            >
              Add line
            </button>
            {ceiling && (
              <p className={`text-xs ${willBreach ? "text-red-700 font-medium" : "text-slate-500"}`} data-testid="ceiling-hint">
                {customer?.tier} / {product?.category} ceiling is {Number(ceiling.ceiling_pct).toFixed(0)}%
                {willBreach && ` — this line is ${(Number(discount) - Number(ceiling.ceiling_pct)).toFixed(1)}pp over`}
              </p>
            )}
          </div>
        </section>
      )}

      {quote && quote.lines.length > 0 && isEditable && (
        <UpsellPanel quoteId={quote.id} onAccept={acceptUpsell} />
      )}

      {quote && quote.lines.length > 0 && (
        <section className="bg-white border border-slate-200 rounded-lg p-4">
          <LineTable
            lines={quote.lines}
            onDelete={isEditable ? removeLine : undefined}
            onUpdateLine={isEditable ? updateLine : undefined}
          />
          {/* §B3: one discount across every line, plus a live margin
              indicator beside the total. The order discount is written onto
              the LINES rather than stored separately -- an order-level field
              would be invisible to the BDRS engine, which scores lines, so a
              rep could set 30% against a 10% ceiling and still score zero. */}
          {isEditable && quote.lines.length > 0 && (
            <div className="flex flex-wrap items-end gap-3 mt-4 pt-3 border-t border-slate-100">
              <label className="text-sm">
                <span className="block text-slate-600 mb-1">Order-level discount %</span>
                <input
                  type="number" min={0} max={100} step="0.5"
                  value={orderDiscount}
                  data-testid="order-discount"
                  onChange={(e) => setOrderDiscount(e.target.value)}
                  className="border border-slate-300 rounded px-2 py-1.5 text-sm w-28"
                />
              </label>
              <button
                onClick={applyOrderDiscount}
                data-testid="apply-order-discount"
                disabled={orderDiscount === ""}
                className="bg-slate-700 text-white rounded px-3 py-1.5 text-sm font-medium disabled:opacity-40"
              >
                Apply to all lines
              </button>
              <p className="text-xs text-slate-500">
                Applies to every line, then re-scores -- the same ceilings and chain apply.
              </p>
            </div>
          )}

          <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-100">
            <div>
              <p className="text-sm text-slate-600">
                Net total{" "}
                <span className="font-semibold text-slate-900 tabular-nums">
                  {currency(quote.totals.net_total)}
                </span>
                <span className="text-slate-400"> · </span>
                Order margin{" "}
                <span
                  data-testid="order-margin"
                  className={`font-semibold tabular-nums ${
                    orderMargin === null ? "text-slate-400"
                    : orderMargin < 15 ? "text-red-700"
                    : orderMargin < 25 ? "text-amber-700"
                    : "text-emerald-700"
                  }`}
                >
                  {orderMargin === null ? "—" : `${orderMargin.toFixed(1)}%`}
                </span>
              </p>
              {quote.state !== "DRAFT" && (
                <p className="text-xs text-slate-500 mt-1">
                  💡 Removing an over-ceiling line will re-score the quote instantly. If BDRS drops below 20, it auto-approves!
                </p>
              )}
            </div>
            {quote.state === "DRAFT" && (
              <button
                onClick={confirm}
                data-testid="confirm"
                className="bg-emerald-700 text-white rounded px-4 py-2 text-sm font-medium hover:bg-emerald-600 transition"
              >
                {isRevisionNeeded ? "Re-submit & score" : "Confirm & score"}
              </button>
            )}
          </div>
        </section>
      )}

      {(score || (quote && quote.risk_score !== null)) && (() => {
        const displayedScore = score ? score.score : Number(quote!.risk_score);
        const isHardStop = score ? score.hard_stop : displayedScore >= 80;
        const verifier = score ? score.verifier_verdict : "PASS";
        const chainText = score
          ? (score.approval_chain.length
              ? <>Routed to <strong>{score.approval_chain.join(" → ").replaceAll("_", " ")}</strong></>
              : <>Auto-approved — no chain required</>)
          : quote!.current_stage
          ? <>Awaiting approval from <strong>{quote!.current_stage.replaceAll("_", " ")}</strong></>
          : displayedScore >= 20
          ? <>Approval chain processed</>
          : <>Compliant terms — auto-approved</>;

        const explanationLines = score
          ? score.explanation
          : quote!.lines.map((ln) =>
              ln.breaches_ceiling
                ? `${ln.product_name}: ${Number(ln.discount_pct).toFixed(1)}% vs ${Number(ln.ceiling_pct_applied).toFixed(0)}% ceiling (+${Number(ln.excess_pp).toFixed(1)}pp breach)`
                : `${ln.product_name}: ${Number(ln.discount_pct).toFixed(1)}% discount within policy`
            );

        return (
          <section className="bg-white border border-slate-200 rounded-lg p-4 shadow-xs" data-testid="score-panel">
            <div className="flex items-center gap-3 mb-3">
              <h3 className="text-sm font-semibold text-slate-700">Governance &amp; Commercial Risk</h3>
              <RiskBadge score={displayedScore} />
              {isHardStop && (
                <span className="bg-red-100 text-red-800 text-xs font-semibold px-2 py-0.5 rounded">
                  HARD STOP
                </span>
              )}
              {score?.concession_review && (
                <span
                  data-testid="concession-badge"
                  className="bg-indigo-100 text-indigo-800 text-xs font-semibold px-2 py-0.5 rounded"
                  title="Every line is within its ceiling, so the score is low — but the order concedes enough value to need a human"
                >
                  VALUE REVIEW · {currency(score.concession)} conceded
                </span>
              )}
              {quote?.risk_band && (
                <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                  {quote.risk_band} RISK
                </span>
              )}
              <span className="text-xs text-slate-500">verifier {verifier}</span>
            </div>
            <p className="text-sm mb-3" data-testid="chain">
              {chainText}
            </p>
            <ul className="text-sm text-slate-700 space-y-1 list-disc pl-5">
              {explanationLines.map((line, i) => <li key={i}>{line}</li>)}
            </ul>
          </section>
        );
      })()}

      {quote && quote.approval_steps.length > 0 && (
        <section className="bg-white border border-slate-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-2">Approval trail</h3>
          <ApprovalTrail steps={quote.approval_steps} />
        </section>
      )}
    </div>
  );
}
