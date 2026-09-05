import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api, type CatalogProduct, type CatalogSummary, type PriceListRef,
  type ProductDetailOut,
} from "@/lib/api";
import { EmptyRow, ErrorBanner, PageHeader, Pagination, StatCard, money } from "./components";

/** Screens 16 & 17 — Product catalog, and the detail view a row opens. */
export default function Catalog() {
  const [summary, setSummary] = useState<CatalogSummary | null>(null);
  const [products, setProducts] = useState<CatalogProduct[]>([]);
  const [selected, setSelected] = useState<ProductDetailOut | null>(null);
  const [category, setCategory] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [draft, setDraft] = useState({
    sku: "", name: "", category: "Hardware", list_price: "", unit_cost: "",
    is_subscription: false, is_promoted: false,
  });

  async function createProduct(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const created = await api.post<ProductDetailOut>("/api/catalog/products", draft);
      setCreating(false);
      setDraft({ ...draft, sku: "", name: "", list_price: "", unit_cost: "" });
      load();
      setSelected(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    api.get<CatalogSummary>("/api/catalog/summary")
      .then(setSummary)
      .catch(() => {});
  }, []);

  const load = useCallback(() => {
    const q = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      ...(category !== "all" ? { category } : {}),
    });
    api.getPaginated<CatalogProduct[]>(`/api/catalog/products?${q.toString()}`)
      .then((res) => {
        setProducts(res.data);
        setTotalCount(res.totalCount);
        setTotalPages(res.totalPages);
      })
      .catch((e) => setError(String(e.message)));
  }, [category, page, pageSize]);

  useEffect(load, [load]);

  const categories = useMemo(
    () => ["Hardware", "Software", "Support", "Services"],
    [],
  );
  const rows = products;

  function open(id: number) {
    setError(null);
    api.get<ProductDetailOut>(`/api/catalog/products/${id}`)
      .then(setSelected)
      .catch((e) => setError(String(e.message)));
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Product catalog"
        subtitle="Every product, variant and price list in one place."
        actions={
          <>
            <select
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setPage(1);
              }}
              className="border border-slate-300 rounded px-2 py-1.5 text-sm"
            >
              <option value="all">All categories</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <button onClick={() => setCreating(!creating)}
              data-testid="toggle-new-product"
              className="bg-slate-900 text-white rounded px-3 py-1.5 text-sm font-medium">
              {creating ? "Cancel" : "+ New product"}
            </button>
          </>
        }
      />
      <ErrorBanner error={error} />

      {creating && (
        <form onSubmit={createProduct}
          className="bg-white border border-slate-200 rounded-lg p-4 grid md:grid-cols-6 gap-3 items-end"
          data-testid="new-product-form">
          {([
            ["sku", "SKU"], ["name", "Name"],
            ["list_price", "List price"], ["unit_cost", "Unit cost"],
          ] as const).map(([field, label]) => (
            <label key={field} className="text-sm">
              <span className="block text-slate-600 mb-1">{label}</span>
              <input
                required
                value={draft[field] as string}
                data-testid={`new-${field}`}
                onChange={(e) => setDraft({ ...draft, [field]: e.target.value })}
                className="border border-slate-300 rounded px-2 py-1.5 text-sm w-full"
              />
            </label>
          ))}
          <label className="text-sm">
            <span className="block text-slate-600 mb-1">Category</span>
            <select value={draft.category}
              onChange={(e) => setDraft({ ...draft, category: e.target.value })}
              className="border border-slate-300 rounded px-2 py-1.5 text-sm w-full">
              {["Hardware", "Software", "Service", "Subscription"].map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>
          <button type="submit" data-testid="create-product"
            className="bg-emerald-700 text-white rounded px-3 py-1.5 text-sm font-medium">
            Create
          </button>
        </form>
      )}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Products" value={summary.total_products}
            hint={`${summary.subscription_products} recurring`} />
          <StatCard label="Variants" value={summary.variants} hint="across all products" />
          <StatCard label="Price lists" value={summary.price_lists}
            hint={summary.currencies.join(", ")} />
          <StatCard label="Categories" value={categories.length} />
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2 font-medium">Product</th>
              <th className="px-4 py-2 font-medium">Category</th>
              <th className="px-4 py-2 font-medium text-right">List price</th>
              <th className="px-4 py-2 font-medium text-right">Margin</th>
              <th className="px-4 py-2 font-medium text-right">Variants</th>
              <th className="px-4 py-2 font-medium text-right">Available</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <EmptyRow colSpan={7} text="No products in this category." />}
            {rows.map((p) => (
              <tr key={p.id} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="px-4 py-2">
                  {p.name}
                  {p.is_promoted && (
                    <span className="ml-2 text-[10px] bg-indigo-100 text-indigo-800 px-1.5 py-0.5 rounded">
                      promoted
                    </span>
                  )}
                  <span className="block text-xs text-slate-400">{p.sku}</span>
                </td>
                <td className="px-4 py-2 text-slate-600">
                  {p.category}
                  {p.is_subscription && (
                    <span className="block text-[10px] text-slate-400">recurring</span>
                  )}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">{money(p.list_price)}</td>
                <td className="px-4 py-2 text-right tabular-nums text-slate-600">{p.margin_pct}%</td>
                <td className="px-4 py-2 text-right tabular-nums text-slate-500">{p.variants || "—"}</td>
                <td className={`px-4 py-2 text-right tabular-nums ${
                  p.qty_available <= 0 ? "text-red-700" : "text-slate-900"}`}>
                  {p.is_subscription ? "—" : p.qty_available}
                </td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => open(p.id)}
                    data-testid={`open-product-${p.id}`}
                    className="text-xs text-slate-600 border border-slate-200 rounded px-2 py-1 hover:bg-white">
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Pagination
        page={page}
        pageSize={pageSize}
        totalCount={totalCount}
        totalPages={totalPages}
        onPageChange={setPage}
        onPageSizeChange={(sz) => {
          setPageSize(sz);
          setPage(1);
        }}
        pageSizeOptions={[10, 20, 50, 100]}
      />

      {selected && (
        <ProductDetail
          product={selected}
          onClose={() => setSelected(null)}
          onChanged={(p) => { setSelected(p); load(); }}
          onError={setError}
        />
      )}
    </div>
  );
}

/** Screen 17 — Product and pricelist. */
function ProductDetail({
  product, onClose, onChanged, onError,
}: {
  product: ProductDetailOut;
  onClose: () => void;
  onChanged: (p: ProductDetailOut) => void;
  onError: (e: string) => void;
}) {
  const [lists, setLists] = useState<PriceListRef[]>([]);
  const [variant, setVariant] = useState({ attribute: "", value: "", extra_price: "0" });
  const [priceEdit, setPriceEdit] = useState({ price_list_id: "", price: "" });

  useEffect(() => {
    api.get<PriceListRef[]>("/api/catalog/price-lists").then(setLists).catch(() => setLists([]));
  }, []);

  async function run<T>(fn: () => Promise<T>) {
    try { onChanged(await fn() as ProductDetailOut); }
    catch (e) { onError(e instanceof Error ? e.message : String(e)); }
  }

  const addVariant = () =>
    run(() => api.post<ProductDetailOut>(
      `/api/catalog/products/${product.id}/variants`, variant));

  const setPrice = () =>
    run(() => api.put<ProductDetailOut>(
      `/api/catalog/products/${product.id}/price-list`,
      { price_list_id: Number(priceEdit.price_list_id), price: priceEdit.price },
    ));

  const field = (label: string, value: React.ReactNode) => (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-sm text-slate-900 mt-0.5">{value}</p>
    </div>
  );

  return (
    <section className="bg-white border border-slate-200 rounded-lg p-5" data-testid="product-detail">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-slate-900">{product.name}</h3>
          <p className="text-xs text-slate-500">{product.sku} · {product.category}</p>
        </div>
        <button onClick={onClose} className="text-sm text-slate-400 hover:text-slate-700">
          Close
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
        {field("List price", money(product.list_price))}
        {field("Unit cost", money(product.unit_cost))}
        {field("Subscription", product.is_subscription ? "Yes" : "No")}
        {/* recurring interval only exists for subscription products */}
        {product.is_subscription
          ? field("Recurring", product.recurring_interval)
          : field("Quantity on hand", product.qty_on_hand)}
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        <div>
          <h4 className="text-sm font-semibold text-slate-700 mb-2">Variants</h4>
          <div className="flex flex-wrap items-end gap-2 mb-3">
            <input placeholder="Attribute" value={variant.attribute}
              data-testid="variant-attribute"
              onChange={(e) => setVariant({ ...variant, attribute: e.target.value })}
              className="border border-slate-300 rounded px-2 py-1 text-sm w-28" />
            <input placeholder="Value" value={variant.value}
              data-testid="variant-value"
              onChange={(e) => setVariant({ ...variant, value: e.target.value })}
              className="border border-slate-300 rounded px-2 py-1 text-sm w-28" />
            <input placeholder="+/- price" value={variant.extra_price}
              data-testid="variant-extra"
              onChange={(e) => setVariant({ ...variant, extra_price: e.target.value })}
              className="border border-slate-300 rounded px-2 py-1 text-sm w-24" />
            <button onClick={addVariant} data-testid="add-variant"
              className="bg-slate-700 text-white rounded px-3 py-1 text-xs font-medium">
              Add variant
            </button>
          </div>

          {product.variants.length === 0 ? (
            <p className="text-sm text-slate-400">No variants configured.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="py-1.5 font-medium">Attribute</th>
                  <th className="py-1.5 font-medium">Values</th>
                </tr>
              </thead>
              <tbody>
                {product.variants.map((v) => (
                  <tr key={v.attribute} className="border-b border-slate-100">
                    <td className="py-1.5 font-medium text-slate-700">{v.attribute}</td>
                    <td className="py-1.5 text-slate-600">
                      {v.values.map((x) => (
                        <span key={x.value} className="inline-block mr-2">
                          {x.value}
                          {Number(x.extra_price) !== 0 && (
                            <span className={Number(x.extra_price) > 0 ? "text-slate-500" : "text-emerald-700"}>
                              {" "}({Number(x.extra_price) > 0 ? "+" : ""}{money(x.extra_price)})
                            </span>
                          )}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div>
          <h4 className="text-sm font-semibold text-slate-700 mb-2">Price lists</h4>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200">
                <th className="py-1.5 font-medium">List</th>
                <th className="py-1.5 font-medium">Currency</th>
                <th className="py-1.5 font-medium text-right">Price</th>
              </tr>
            </thead>
            <tbody>
              {product.price_lists.map((pl) => (
                <tr key={pl.name} className="border-b border-slate-100">
                  <td className="py-1.5">{pl.name}</td>
                  <td className="py-1.5 text-slate-500">{pl.currency}</td>
                  <td className="py-1.5 text-right tabular-nums">{money(pl.price)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="flex flex-wrap items-end gap-2 mt-3">
            <select value={priceEdit.price_list_id}
              data-testid="price-list-select"
              onChange={(e) => setPriceEdit({ ...priceEdit, price_list_id: e.target.value })}
              className="border border-slate-300 rounded px-2 py-1 text-sm">
              <option value="">Price list…</option>
              {lists.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
            <input placeholder="Price" value={priceEdit.price}
              data-testid="price-value"
              onChange={(e) => setPriceEdit({ ...priceEdit, price: e.target.value })}
              className="border border-slate-300 rounded px-2 py-1 text-sm w-28" />
            <button onClick={setPrice} data-testid="set-price"
              disabled={!priceEdit.price_list_id || !priceEdit.price}
              className="bg-slate-700 text-white rounded px-3 py-1 text-xs font-medium disabled:opacity-40">
              Set price
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
