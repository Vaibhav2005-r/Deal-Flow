import { useState } from "react";
import { api } from "@/lib/api";
import { setToken } from "@/lib/auth";

const DEMO = [
  { email: "priya.raghavan@dealflow.example", label: "Priya Raghavan · rep" },
  { email: "james.whitfield@dealflow.example", label: "James Whitfield · manager" },
  { email: "aisha.karim@dealflow.example", label: "Aisha Karim · finance" },
];

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [email, setEmail] = useState(DEMO[0].email);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // seeded demo accounts use the email as the password
      const res = await api.post<{ token: string; role: string; full_name: string; user_id: number }>(
        "/api/auth/login", { email, password: email },
      );
      setToken("internal", res.token);
      localStorage.setItem("df360.internal.user", JSON.stringify(res));
      onLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <form onSubmit={submit} className="bg-white p-8 rounded-lg shadow-sm w-full max-w-md border border-slate-200">
        <h1 className="text-2xl font-semibold text-slate-900">DealFlow360</h1>
        <p className="text-sm text-slate-500 mt-1 mb-6">Internal console</p>

        <label className="block text-sm font-medium text-slate-700 mb-1">Sign in as</label>
        <select
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full border border-slate-300 rounded px-3 py-2 mb-4 text-sm"
        >
          {DEMO.map((d) => (
            <option key={d.email} value={d.email}>{d.label}</option>
          ))}
        </select>

        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full bg-slate-900 text-white rounded px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
