import { useEffect, useState } from "react";
import { api, type Customer, type Policy, type Product, type Quote, type Score } from "@/lib/api";
import { ApprovalTrail, LineTable, RiskBadge, StateBadge } from "./components";

export default function QuoteBuilder() {
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
      setCustomerId(c.find((x) => x.tier === "gold")?.id ?? c[0]?.id ?? null);
      setProductId(p.find((x) => x.sku === "SV-INST-01")?.id ?? p[0]?.id ?? null);
    }).catch((e) => setError(String(e.message)));
  }, []);

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
      setQuote(q); setScore(null);
    });

  const addLine = () =>
    run(async () => {
      if (!quote || !productId) return;
      const q = await api.post<Quote>(`/api/quotes/${quote.id}/lines`, {
        product_id: productId, qty, discount_pct: discount,
      });
      setQuote(q);
    });

  const confirm = () =>
    run(async () => {
      if (!quote) return;
      const s = await api.post<Score>(`/api/quotes/${quote.id}/confirm`, {});
      setScore(s);
      setQuote(await api.get<Quote>(`/api/quotes/${quote.id}`));
    });

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h2 className="text-xl font-semibold text-slate-900">Quote builder</h2>
        {quote && (
          <div className="flex items-center gap-2">
            <StateBadge state={quote.state} />
            <RiskBadge score={quote.risk_score ? Number(quote.risk_score) : null} />
          </div>
        )}
      </div>

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
            onClick={createQuote}
            data-testid="new-quote"
            className="bg-slate-900 text-white rounded px-3 py-1.5 text-sm font-medium"
          >
            {quote ? "Start another" : "New quote"}
          </button>
          {quote && <span className="text-sm text-slate-500">Quote #{quote.id} · v{quote.version}</span>}
        </div>
      </section>

      {quote && (
        <section className="bg-white border border-slate-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Add a line</h3>
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
              className="bg-slate-700 text-white rounded px-3 py-1.5 text-sm font-medium"
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

      {quote && quote.lines.length > 0 && (
        <section className="bg-white border border-slate-200 rounded-lg p-4">
          <LineTable lines={quote.lines} />
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-slate-600">
              Net total{" "}
              <span className="font-semibold text-slate-900 tabular-nums">
                {new Intl.NumberFormat("en-IN").format(Number(quote.totals.net_total))}
              </span>
            </p>
            {quote.state === "DRAFT" && (
              <button
                onClick={confirm}
                data-testid="confirm"
                className="bg-emerald-700 text-white rounded px-4 py-2 text-sm font-medium"
              >
                Confirm &amp; score
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
