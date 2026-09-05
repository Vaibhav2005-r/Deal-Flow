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
import { ApprovalTrail, LineTable, RiskBadge, StateBadge } from "./components";
import UpsellPanel from "./UpsellPanel";

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
    quote.state === "UNDER_NEGOTIATION";

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
          <div className="flex items-center gap-2">
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

      {quote && (quote.state === "READY_TO_FULFILL" || quote.legal_events?.includes("send_to_portal")) && (
        <div className="bg-gradient-to-r from-emerald-50 to-teal-50 border border-emerald-300 rounded-lg p-4 flex flex-wrap items-center justify-between gap-3 shadow-xs">
          <div>
            <h4 className="text-sm font-bold text-emerald-950 flex items-center gap-2">
              <span>🚀 Quotation Approved &amp; Ready for Customer</span>
            </h4>
            <p className="text-xs text-emerald-800 mt-0.5">
              Deliver this approved quotation to the customer portal so they can review, negotiate, or accept terms.
            </p>
          </div>
          <button
            onClick={sendToPortal}
            disabled={busy}
            className="bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-bold px-4 py-2 rounded-lg shadow-sm transition disabled:opacity-50"
          >
            {busy ? "Sending…" : "Send to Customer Portal →"}
          </button>
        </div>
      )}

      {quote && (quote.state === "UNDER_NEGOTIATION" || messages.length > 0) && (() => {
        const counterMsgs = messages.filter((m) => m.counter_discount_pct !== null);
        const latestCounter = counterMsgs.length > 0 ? counterMsgs[counterMsgs.length - 1] : null;
        const counterLine = latestCounter ? quote.lines.find((l) => l.id === latestCounter.quote_line_id) : null;

        return (
          <section className="bg-white border-2 border-purple-200 rounded-lg p-5 shadow-xs space-y-4" data-testid="negotiation-panel">
            <div className="flex items-center justify-between border-b border-purple-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-base font-bold text-purple-950">💬 Customer Portal Negotiation</span>
                {quote.state === "UNDER_NEGOTIATION" && (
                  <span className="bg-purple-100 text-purple-800 border border-purple-200 text-xs font-semibold px-2.5 py-0.5 rounded-full animate-pulse">
                    Active Counter-Proposal
                  </span>
                )}
              </div>
              <span className="text-xs text-slate-500 font-medium">
                {messages.length} message{messages.length === 1 ? "" : "s"} in thread
              </span>
            </div>

            {quote.state === "UNDER_NEGOTIATION" && latestCounter && (
              <div className="bg-purple-50 border border-purple-300 rounded-lg p-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h4 className="text-sm font-bold text-purple-950">
                      Customer Requested Counter-Discount: {Number(latestCounter.counter_discount_pct).toFixed(1)}%
                      {counterLine && <span className="text-purple-700 font-normal"> on {counterLine.product_name}</span>}
                    </h4>
                    <p className="text-xs text-purple-800 mt-1 italic bg-white/70 border border-purple-200 p-2 rounded">
                      "{latestCounter.body}"
                    </p>
                    <p className="text-xs text-purple-700 mt-2">
                      💡 <strong>1-Click Resolution:</strong> Accepting will apply {Number(latestCounter.counter_discount_pct).toFixed(1)}% to the targeted line, void previous approvals, and re-score the quote immediately.
                    </p>
                  </div>
                  <button
                    onClick={acceptCounter}
                    disabled={busy}
                    data-testid="accept-counter"
                    className="shrink-0 bg-purple-700 hover:bg-purple-800 text-white rounded-lg px-4 py-2.5 text-xs font-bold shadow-sm transition disabled:opacity-50"
                  >
                    {busy ? "Applying…" : `⚡ Accept Counter (${Number(latestCounter.counter_discount_pct).toFixed(1)}%)`}
                  </button>
                </div>
              </div>
            )}

            {/* Messages discussion thread */}
            {messages.length > 0 && (
              <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {messages.map((m) => {
                  const mLine = m.quote_line_id ? quote.lines.find((l) => l.id === m.quote_line_id) : null;
                  return (
                    <div key={m.id} className="bg-slate-50 border border-slate-200 rounded p-3 text-xs space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-800">{m.author_name}</span>
                        <span className="text-[11px] text-slate-400 tabular-nums">{m.created_at.slice(0, 19).replace("T", " ")}</span>
                      </div>
                      <p className="text-slate-700">{m.body}</p>
                      {m.counter_discount_pct && (
                        <div className="pt-1">
                          <span className="inline-block bg-purple-100 text-purple-800 text-[11px] font-semibold px-2 py-0.5 rounded">
                            Proposed {Number(m.counter_discount_pct).toFixed(1)}% discount {mLine ? `on ${mLine.product_name}` : ""}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Rep reply input */}
            <form onSubmit={postReply} className="flex gap-2 pt-2 border-t border-purple-100">
              <input
                type="text"
                placeholder="Post a reply or counter-response to the customer portal…"
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                className="flex-1 border border-slate-300 rounded px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <button
                type="submit"
                disabled={busy || !replyText.trim()}
                className="bg-slate-900 hover:bg-slate-800 text-white rounded px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50"
              >
                Send Reply
              </button>
            </form>
          </section>
        );
      })()}

      <section className="bg-white border border-slate-200 rounded-lg p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="block text-slate-600 mb-1">Customer</span>
            <select
              data-testid="customer"
              className="border border-slate-300 rounded px-2 py-1.5 text-sm min-w-64"
              value={customerId ?? ""}
              onChange={(e) => setCustomerId(Number(e.target.value))}
              disabled={!!quote}
            >
              {customers.map((c) => (
                <option key={c.id} value={c.id}>{c.name} · {c.tier}</option>
              ))}
            </select>
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
              <select
                data-testid="product"
                className="border border-slate-300 rounded px-2 py-1.5 text-sm min-w-72"
                value={productId ?? ""}
                onChange={(e) => setProductId(Number(e.target.value))}
              >
                {products.map((p) => (
                  <option key={p.id} value={p.id}>{p.name} · {p.category}</option>
                ))}
              </select>
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
                  ₹{new Intl.NumberFormat("en-IN").format(Number(quote.totals.net_total))}
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
                  VALUE REVIEW · {new Intl.NumberFormat("en-IN").format(score.concession)} conceded
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
