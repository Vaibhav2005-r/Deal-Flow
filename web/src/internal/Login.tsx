import { useState } from "react";
import { api } from "@/lib/api";
import { setToken } from "@/lib/auth";

const DEMO = [
  { email: "priya.raghavan@dealflow.example", label: "Priya Raghavan · rep", role: "rep" },
  { email: "daniel.okafor@dealflow.example", label: "Daniel Okafor · rep", role: "rep" },
  { email: "sofia.marchetti@dealflow.example", label: "Sofia Marchetti · rep", role: "rep" },
  { email: "james.whitfield@dealflow.example", label: "James Whitfield · manager", role: "manager" },
  { email: "aisha.karim@dealflow.example", label: "Aisha Karim · finance", role: "finance" },
  { email: "root@dealflow.example", label: "System Administrator · admin", role: "admin" },
];

type Mode = "login" | "signup";

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState(DEMO[0].email);
  const [loginPassword, setLoginPassword] = useState(DEMO[0].email);
  const [signupEmail, setSignupEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function selectDemoUser(demoEmail: string) {
    setEmail(demoEmail);
    // Seeded accounts use their email address as their default password
    setLoginPassword(demoEmail);
  }

  function accept(res: { token: string; role: string; full_name: string; user_id: number }) {
    setToken("internal", res.token);
    localStorage.setItem("df360.internal.user", JSON.stringify(res));
    onLogin();
  }

  async function submitSignup(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      accept(await api.post("/api/auth/signup", {
        email: signupEmail, full_name: fullName, password,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "sign up failed");
    } finally {
      setBusy(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      accept(await api.post("/api/auth/login", { email, password: loginPassword }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "login failed");
    } finally {
      setBusy(false);
    }
  }

  if (mode === "signup") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100">
        <form onSubmit={submitSignup} className="bg-white p-8 rounded-lg shadow-sm w-full max-w-md border border-slate-200">
          <h1 className="text-2xl font-semibold text-slate-900">DealFlow360</h1>
          <p className="text-sm text-slate-500 mt-1 mb-4">Create an account</p>

          <div className="flex gap-1 mb-5">
            {(["login", "signup"] as Mode[]).map((m) => (
              <button
                key={m} type="button" onClick={() => { setMode(m); setError(null); }}
                data-testid={`mode-${m}`}
                className={`px-3 py-1.5 text-sm rounded ${
                  mode === m ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {m === "login" ? "Log in" : "Sign up"}
              </button>
            ))}
          </div>

          <label className="block text-sm font-medium text-slate-700 mb-1">Full name</label>
          <input value={fullName} onChange={(e) => setFullName(e.target.value)}
            data-testid="signup-name" required minLength={2}
            className="w-full border border-slate-300 rounded px-3 py-2 mb-3 text-sm" />

          <label className="block text-sm font-medium text-slate-700 mb-1">Work email</label>
          <input type="email" value={signupEmail} onChange={(e) => setSignupEmail(e.target.value)}
            data-testid="signup-email" required
            className="w-full border border-slate-300 rounded px-3 py-2 mb-3 text-sm" />

          <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            data-testid="signup-password" required minLength={8}
            className="w-full border border-slate-300 rounded px-3 py-2 mb-1 text-sm" />
          <p className="text-xs text-slate-400 mb-4">
            At least 8 characters. New accounts are created as a sales rep —
            approver roles are granted by an admin.
          </p>

          {error && <p className="text-sm text-red-600 mb-3" data-testid="signup-error">{error}</p>}

          <button type="submit" disabled={busy}
            data-testid="signup-submit"
            className="w-full bg-slate-900 text-white rounded px-4 py-2 text-sm font-medium disabled:opacity-50">
            {busy ? "Creating…" : "Create account"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <form onSubmit={submit} className="bg-white p-8 rounded-lg shadow-sm w-full max-w-md border border-slate-200">
        <h1 className="text-2xl font-semibold text-slate-900">DealFlow360</h1>
        <p className="text-sm text-slate-500 mt-1 mb-4">Internal console</p>

        <div className="flex gap-1 mb-5">
          {(["login", "signup"] as Mode[]).map((m) => (
            <button
              key={m} type="button" onClick={() => { setMode(m); setError(null); }}
              data-testid={`mode-${m}`}
              className={`px-3 py-1.5 text-sm rounded ${
                mode === m ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {m === "login" ? "Log in" : "Sign up"}
            </button>
          ))}
        </div>

        <label className="block text-sm font-medium text-slate-700 mb-1">Quick demo profile</label>
        <select
          value={email}
          onChange={(e) => selectDemoUser(e.target.value)}
          className="w-full border border-slate-300 rounded px-3 py-2 mb-4 text-sm bg-slate-50 font-medium"
        >
          {DEMO.map((d) => (
            <option key={d.email} value={d.email}>{d.label}</option>
          ))}
        </select>

        <div className="border-t border-slate-100 pt-3 mb-4 space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Work email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Password</label>
            <input
              type="password"
              value={loginPassword}
              onChange={(e) => setLoginPassword(e.target.value)}
              required
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            />
            <p className="text-[11px] text-slate-400 mt-1">
              For demo presets, the default password is the user's email address.
            </p>
          </div>
        </div>

        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full bg-slate-900 hover:bg-slate-800 text-white rounded px-4 py-2 text-sm font-medium disabled:opacity-50 transition"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <div className="mt-5 pt-4 border-t border-slate-200 text-center">
          <p className="text-xs text-slate-500">
            Testing customer negotiation?{" "}
            <a
              href="/portal/login"
              className="font-semibold text-indigo-600 hover:text-indigo-800 hover:underline"
            >
              Switch to Customer Portal Login →
            </a>
          </p>
        </div>
      </form>
    </div>
  );
}
