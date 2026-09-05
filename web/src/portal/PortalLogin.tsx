import { useState } from "react";
import { api } from "@/lib/api";
import { setToken } from "@/lib/auth";

const DEMO_PORTAL_USERS = [
  {
    email: "portal1@northwind.example",
    password: "Northwind Logistics Pvt Ltd",
    label: "Northwind Logistics (Gold Tier)",
  },
  {
    email: "portal2@harbourline.example",
    password: "Harbourline Shipping",
    label: "Harbourline Shipping (Gold Tier)",
  },
  {
    email: "portal3@calder.example",
    password: "Calder & Voss Associates",
    label: "Calder & Voss Associates (Gold Tier)",
  },
];

interface PortalLoginProps {
  onLogin: () => void;
}

export default function PortalLogin({ onLogin }: PortalLoginProps) {
  const [selectedDemo, setSelectedDemo] = useState(0);
  const [email, setEmail] = useState(DEMO_PORTAL_USERS[0].email);
  const [password, setPassword] = useState(DEMO_PORTAL_USERS[0].password);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function handleSelectDemo(index: number) {
    setSelectedDemo(index);
    setEmail(DEMO_PORTAL_USERS[index].email);
    setPassword(DEMO_PORTAL_USERS[index].password);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<{
        token: string;
        scope: string;
        role: string;
        full_name: string;
        user_id: number;
      }>("/api/auth/login", { email, password }, "portal");

      if (res.scope !== "portal") {
        throw new Error("Invalid credentials for customer portal");
      }

      setToken("portal", res.token);
      localStorage.setItem("df360.portal.user", JSON.stringify(res));
      onLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Portal login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <div className="bg-white p-8 rounded-xl shadow-md w-full max-w-md border border-slate-200">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-lg">
            DF
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">DealFlow360</h1>
            <p className="text-xs font-medium text-indigo-600 uppercase tracking-wider">
              Customer Negotiation Portal
            </p>
          </div>
        </div>

        <p className="text-sm text-slate-600 mb-6">
          Sign in to review quotations, propose counter-discounts, and confirm terms.
        </p>

        <div className="mb-5">
          <label className="block text-xs font-semibold text-slate-600 mb-1">
            Quick Select Demo Customer
          </label>
          <select
            value={selectedDemo}
            onChange={(e) => handleSelectDemo(Number(e.target.value))}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-slate-50 hover:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-800"
          >
            {DEMO_PORTAL_USERS.map((d, i) => (
              <option key={d.email} value={i}>
                {d.label}
              </option>
            ))}
          </select>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">
              Email Address
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors disabled:opacity-50 shadow-sm"
          >
            {busy ? "Signing in…" : "Sign In to Portal"}
          </button>
        </form>

        <div className="mt-6 pt-4 border-t border-slate-100 text-center">
          <span className="text-xs text-slate-400">
            Secure Portal Session · Scope: portal
          </span>
        </div>
      </div>
    </div>
  );
}
