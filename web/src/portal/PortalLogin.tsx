import { useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { api } from "@/lib/api";
import { setToken } from "@/lib/auth";

/**
 * No pre-filled credentials.
 *
 * This list held real customer logins in plain text, rendered into the page.
 * Customers sign in with their own credentials, the same as anywhere else --
 * and the main sign-in form now routes portal accounts here automatically, so
 * a shortcut list is not needed to reach this screen.
 */

interface PortalLoginProps {
  onLogin: () => void;
}

export default function PortalLogin({ onLogin }: PortalLoginProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const shouldReduceMotion = useReducedMotion();


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
      <motion.div
        initial={shouldReduceMotion ? { opacity: 1 } : { opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", damping: 25, stiffness: 240 }}
        className="bg-white p-8 rounded-xl shadow-md w-full max-w-md border border-slate-200"
      >
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-lg shadow-xs">
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
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-2xs focus:shadow-xs transition-all duration-200"
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
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-2xs focus:shadow-xs transition-all duration-200"
            />
          </div>

          <AnimatePresence>
            {error && (
              <motion.div
                initial={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, y: -6 }}
                animate={shouldReduceMotion ? { opacity: 1 } : { opacity: 1, y: 0, x: [0, -4, 4, -3, 3, 0] }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.3 }}
                className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700"
              >
                {error}
              </motion.div>
            )}
          </AnimatePresence>

          <motion.button
            type="submit"
            disabled={busy}
            whileHover={shouldReduceMotion || busy ? {} : { scale: 1.01 }}
            whileTap={shouldReduceMotion || busy ? {} : { scale: 0.99 }}
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors disabled:opacity-50 shadow-sm cursor-pointer"
          >
            {busy ? "Signing in…" : "Sign In to Portal"}
          </motion.button>
        </form>

        <div className="mt-6 pt-4 border-t border-slate-100 text-center">
          <span className="text-xs text-slate-400">
            Secure Portal Session · Scope: portal
          </span>
        </div>
      </motion.div>
    </div>
  );
}
