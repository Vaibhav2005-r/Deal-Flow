import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type Customer, type Policy, type Product, type Quote, type Score } from "@/lib/api";
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

  const [customerId, setCustomerId] = useState<number | null>(null);
  const [productId, setProductId] = useState<number | null>(null);
  const [qty, setQty] = useState(1);
  const [discount, setDiscount] = useState("18");

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

  useEffect(() => {
    if (!id) {
      setQuote(null);
      setScore(null);
      return;
    }
    run(async () => {
      const q = await api.get<Quote>(`/api/quotes/${id}`);
      setQuote(q);
      setCustomerId(q.customer_id);
      setScore(null);
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

  const lastReturnedStep = quote?.approval_steps
    ?.slice()
    .reverse()
    .find((s) => s.decision === "RETURNED");
  const isRevisionNeeded = quote?.state === "DRAFT" && !!lastReturnedStep;
  const isEditable =
    !quote ||
    quote.state === "DRAFT" ||
    quote.state === "PENDING_MANAGER" ||
    quote.state === "PENDING_FINANCE";

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

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-sm rounded px-3 py-2" data-testid="error">
          {error}
        </div>
      )}

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
          <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-100">
            <div>
              <p className="text-sm text-slate-600">
                Net total{" "}
                <span className="font-semibold text-slate-900 tabular-nums">
                  ₹{new Intl.NumberFormat("en-IN").format(Number(quote.totals.net_total))}
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

      {score && (
        <section className="bg-white border border-slate-200 rounded-lg p-4" data-testid="score-panel">
          <div className="flex items-center gap-3 mb-3">
            <h3 className="text-sm font-semibold text-slate-700">Governance result</h3>
            <RiskBadge score={score.score} />
            {score.hard_stop && (
              <span className="bg-red-100 text-red-800 text-xs font-semibold px-2 py-0.5 rounded">
                HARD STOP
              </span>
            )}
            <span className="text-xs text-slate-500">verifier {score.verifier_verdict}</span>
          </div>
          <p className="text-sm mb-3" data-testid="chain">
            {score.approval_chain.length
              ? <>Routed to <strong>{score.approval_chain.join(" → ").replaceAll("_", " ")}</strong></>
              : <>Auto-approved — no chain required</>}
          </p>
          <ul className="text-sm text-slate-700 space-y-1 list-disc pl-5">
            {score.explanation.map((line, i) => <li key={i}>{line}</li>)}
          </ul>
        </section>
      )}

      {quote && quote.approval_steps.length > 0 && (
        <section className="bg-white border border-slate-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-2">Approval trail</h3>
          <ApprovalTrail steps={quote.approval_steps} />
        </section>
      )}
    </div>
  );
}
