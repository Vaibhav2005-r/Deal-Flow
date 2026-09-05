/** Internal router tree — rep + manager + finance + admin. */

import { useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { clearToken, hasScope } from "@/lib/auth";
import Approvals from "./Approvals";
import Login from "./Login";
import QuoteBuilder from "./QuoteBuilder";
import QuoteList from "./QuoteList";

function currentUser(): { full_name: string; role: string } | null {
  try {
    const raw = localStorage.getItem("df360.internal.user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

const tab = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 text-sm rounded ${isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-200"}`;

export default function InternalRouter() {
  const [authed, setAuthed] = useState(hasScope("internal"));
  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  const user = currentUser();

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center gap-4">
          <span className="font-semibold text-slate-900">DealFlow360</span>
          <nav className="flex gap-1">
            <NavLink to="/" end className={tab}>Build</NavLink>
            <NavLink to="/quotes" className={tab}>Quotes</NavLink>
            <NavLink to="/approvals" className={tab}>Approvals</NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className="text-sm text-slate-600" data-testid="whoami">
              {user?.full_name} · {user?.role}
            </span>
            <button
              onClick={() => { clearToken("internal"); setAuthed(false); }}
              className="text-sm text-slate-500 hover:text-slate-900"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-6">
        <Routes>
          <Route index element={<QuoteBuilder />} />
          <Route path="quotes" element={<QuoteList />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
