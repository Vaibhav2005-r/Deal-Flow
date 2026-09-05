import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type CatalogProduct,
  type CatalogSummary,
  type ProductDetailOut,
} from "@/lib/api";
import {
  EmptyRow,
  ErrorBanner,
  PageHeader,
  Pagination,
  StatCard,
  money,
} from "./components";

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
    sku: "",
    name: "",
    category: "Hardware",
    list_price: "",
    unit_cost: "",
    is_subscription: false,
    is_promoted: false,
  });

  async function createProduct(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const created = await api.post<ProductDetailOut>("/api/catalog/products", draft);
      setCreating(false);
      setDraft({
        sku: "",
        name: "",
        category: "Hardware",
        list_price: "",
        unit_cost: "",
        is_subscription: false,
        is_promoted: false,
      });
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
    []
  );

  function open(id: number) {
    setError(null);
    api.get<ProductDetailOut>(`/api/catalog/products/${id}`)
      .then(setSelected)
      .catch((e) => setError(String(e.message)));
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Product & Price Catalog"
        subtitle="Manage sellable SKUs, recurring product configurations, list pricing, and margin baselines."
        actions={
          <div className="flex items-center gap-2.5">
            <select
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setPage(1);
              }}
              className="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-800 font-semibold focus:outline-none focus:ring-1 focus:ring-[#1d72f2] shadow-2xs cursor-pointer"
            >
              <option value="all">All Categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setCreating(!creating)}
              data-testid="toggle-new-product"
              className="bg-[#1d72f2] hover:bg-[#155fc7] text-white rounded-lg px-3.5 py-1.5 text-xs font-semibold shadow-2xs transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              <span>{creating ? "Cancel" : "+ New Product"}</span>
            </button>
          </div>
        }
      />

      <ErrorBanner error={error} />

      {/* Catalog KPI Statistics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard
          label="Total Products"
          value={summary?.total_products ?? (totalCount || products.length)}
        />
        <StatCard
          label="Recurring Plans"
          value={summary?.subscription_products ?? products.filter((p) => p.is_subscription).length}
          tone="emerald"
        />
        <StatCard
          label="Categories"
          value={categories.length}
        />
        <StatCard
          label="Price Lists"
          value={summary?.price_lists ?? 3}
          tone="indigo"
        />
      </div>

      {/* New Product Form Drawer */}
      {creating && (
        <form
          onSubmit={createProduct}
          className="bg-white border border-slate-200/90 rounded-xl p-6 shadow-sm space-y-4"
        >
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <h3 className="text-sm font-bold text-slate-900">Add New Product to Catalog</h3>
            <span className="text-xs text-slate-500">Configure base unit pricing</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">SKU</label>
              <input
                type="text"
                required
                placeholder="e.g. HW-SRV-01"
                value={draft.sku}
                onChange={(e) => setDraft({ ...draft, sku: e.target.value })}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:bg-white focus:outline-none focus:ring-1 focus:ring-[#1d72f2]"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Product Name</label>
              <input
                type="text"
                required
                placeholder="e.g. Enterprise Server Rack"
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:bg-white focus:outline-none focus:ring-1 focus:ring-[#1d72f2]"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Category</label>
              <select
                value={draft.category}
                onChange={(e) => setDraft({ ...draft, category: e.target.value })}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:bg-white focus:outline-none focus:ring-1 focus:ring-[#1d72f2]"
              >
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">List Price ($)</label>
              <input
                type="number"
                step="0.01"
                required
                placeholder="1000.00"
                value={draft.list_price}
                onChange={(e) => setDraft({ ...draft, list_price: e.target.value })}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:bg-white focus:outline-none focus:ring-1 focus:ring-[#1d72f2]"
              />
            </div>
          </div>

          <div className="flex items-center gap-4 pt-2">
            <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
              <input
                type="checkbox"
                checked={draft.is_subscription}
                onChange={(e) => setDraft({ ...draft, is_subscription: e.target.checked })}
                className="rounded border-slate-300 text-[#1d72f2] focus:ring-0"
              />
              <span>Recurring Subscription Product</span>
            </label>

            <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
              <input
                type="checkbox"
                checked={draft.is_promoted}
                onChange={(e) => setDraft({ ...draft, is_promoted: e.target.checked })}
                className="rounded border-slate-300 text-[#1d72f2] focus:ring-0"
              />
              <span>Featured / Promoted</span>
            </label>
          </div>

          <div className="flex justify-end gap-2.5 pt-3 border-t border-slate-100">
            <button
              type="button"
              onClick={() => setCreating(false)}
              className="px-3.5 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-1.5 rounded-lg bg-[#1d72f2] text-white text-xs font-semibold hover:bg-[#155fc7] transition-colors shadow-2xs"
            >
              Save Product
            </button>
          </div>
        </form>
      )}

      {/* Catalog Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50/80 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
              <tr>
                <th className="px-4 py-3">SKU</th>
                <th className="px-4 py-3">Product Name</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Model</th>
                <th className="px-4 py-3 text-right">List Price</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-sans">
              {products.length === 0 ? (
                <EmptyRow colSpan={6} text="No products found in this category." />
              ) : (
                products.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-4 py-3 font-mono font-bold text-slate-900">{p.sku}</td>
                    <td className="px-4 py-3 font-semibold text-slate-900">{p.name}</td>
                    <td className="px-4 py-3">
                      <span className="inline-block px-2.5 py-0.5 rounded-md text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                        {p.category}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {p.is_subscription ? (
                        <span className="text-emerald-700 font-semibold">Recurring</span>
                      ) : (
                        <span className="text-slate-500">One-time</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-slate-900 tabular-nums">
                      ${money(p.list_price)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => open(p.id)}
                        className="text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-md px-3 py-1 transition-colors shadow-2xs cursor-pointer"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
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
      />

      {/* Product Detail Modal / Inspector */}
      {selected && (
        <section className="bg-white border border-slate-200/90 rounded-xl p-6 shadow-md space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h2 className="text-base font-bold text-slate-900">
                {selected.sku} — {selected.name}
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Category: {selected.category} · Standard List: ${money(selected.list_price)}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="text-xs font-semibold text-slate-500 hover:text-slate-800 bg-slate-100 px-3 py-1 rounded-md"
            >
              Close
            </button>
          </div>

          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
              Tier Price List Overrides
            </h3>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-50 font-semibold text-slate-500 border-b border-slate-200">
                  <tr>
                    <th className="py-2 px-3">Price List</th>
                    <th className="py-2 px-3">Currency</th>
                    <th className="py-2 px-3 text-right">Computed Tier Price</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {selected.price_lists?.map((pl, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/70">
                      <td className="py-2 px-3 font-semibold text-slate-800">{pl.name}</td>
                      <td className="py-2 px-3 text-slate-600 uppercase font-mono">{pl.currency}</td>
                      <td className="py-2 px-3 text-right font-bold text-slate-900 tabular-nums">
                        ${money(pl.price)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
