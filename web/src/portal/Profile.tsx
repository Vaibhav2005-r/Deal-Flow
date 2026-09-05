import { api, type PortalProfile } from "@/lib/api";
import { useLiveData } from "@/lib/live";

/**
 * Screen 11, Profile tab.
 *
 * Every value is read from the database. A field with nothing on file renders
 * as "Not on file" rather than a plausible-looking placeholder — a profile
 * padded with invented detail is indistinguishable from a broken one.
 */
export default function Profile() {
  const { data, error, initialLoading } = useLiveData<PortalProfile>(
    () => api.get<PortalProfile>("/api/portal/profile", "portal"),
    [],
    30_000,
  );

  if (initialLoading) return <p className="text-sm text-slate-400">Loading…</p>;
  if (error && !data) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-800 text-sm rounded px-3 py-2">
        {error}
      </div>
    );
  }
  if (!data) return null;

  const field = (label: string, value: string | null) => (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`text-sm mt-0.5 ${value ? "text-slate-900" : "text-slate-400 italic"}`}>
        {value ?? "Not on file"}
      </p>
    </div>
  );

  const money = (v: string) =>
    new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(Number(v));

  return (
    <div className="space-y-5" data-testid="portal-profile">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">{data.name}</h2>
        <p className="text-sm text-slate-500">
          <span className="uppercase tracking-wide">{data.tier}</span> tier
          {data.customer_since && ` · customer since ${data.customer_since}`}
        </p>
      </div>

      <section className="bg-white border border-slate-200 rounded-lg p-5">
        <h3 className="text-sm font-semibold text-slate-700 mb-4">Account contact</h3>
        <div className="grid sm:grid-cols-2 gap-4">
          {field("Contact name", data.contact_name)}
          {field("Email", data.contact_email)}
          {field("Phone", data.contact_phone)}
          {field("Billing address", data.billing_address)}
        </div>
      </section>

      <section className="bg-white border border-slate-200 rounded-lg p-5">
        <h3 className="text-sm font-semibold text-slate-700 mb-4">Your account</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            ["Quotations", String(data.totals.quotations)],
            ["Open now", String(data.totals.open_quotations)],
            ["Invoices", String(data.totals.invoices)],
            ["Outstanding", money(data.totals.outstanding)],
          ].map(([label, value]) => (
            <div key={label}>
              <p className="text-xs text-slate-500">{label}</p>
              <p className="text-lg font-semibold text-slate-900 mt-0.5">{value}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-400 mt-4">
          To change these details, reply on any quotation and your account
          manager will update them.
        </p>
      </section>
    </div>
  );
}
