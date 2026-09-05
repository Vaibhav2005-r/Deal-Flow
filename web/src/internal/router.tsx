/** Internal router tree — rep + manager + finance + admin. */

import { useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { clearToken, hasScope } from "@/lib/auth";
import Approvals from "./Approvals";
import Catalog from "./Catalog";
import Dashboard from "./Dashboard";
import DiscountConfig from "./DiscountConfig";
import FulfillmentList from "./FulfillmentList";
import Invoices from "./Invoices";
import Subscriptions from "./Subscriptions";
import HealthDashboard from "./HealthDashboard";
import Login from "./Login";
import Pipeline from "./Pipeline";
import QuoteBuilder from "./QuoteBuilder";
import QuoteList from "./QuoteList";
import ReliabilityPanel from "./ReliabilityPanel";
import Reports from "./Reports";

function currentUser(): { full_name: string; role: string } | null {
  try {
    const raw = localStorage.getItem("df360.internal.user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

const tab = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors whitespace-nowrap ${
    isActive ? "bg-slate-900 text-white shadow-sm" : "text-slate-600 hover:bg-slate-200"
  }`;

export default function InternalRouter() {
  const [authed, setAuthed] = useState(hasScope("internal"));
  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  const user = currentUser();

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs">
        <div className="max-w-7xl mx-auto px-6 py-2.5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-5">
            <span className="font-bold text-slate-900 text-sm tracking-tight">DealFlow360</span>
            <nav className="flex gap-1 overflow-x-auto py-0.5">
              {/* Order mirrors the product flow: home, sell, approve, fulfil,
                  bill, then the analysis and admin surfaces. */}
              <NavLink to="/" end className={tab}>Home</NavLink>
              <NavLink to="/build" className={tab}>Build</NavLink>
              <NavLink to="/quotes" className={tab}>Quotations</NavLink>
              <NavLink to="/approvals" className={tab}>Approvals</NavLink>
              <NavLink to="/fulfillment" className={tab}>Fulfillment</NavLink>
              <NavLink to="/subscriptions" className={tab}>Subscriptions</NavLink>
              <NavLink to="/invoices" className={tab}>Invoices</NavLink>
              <NavLink to="/health" className={tab}>Deal Health</NavLink>
              <NavLink to="/reports" className={tab}>Reports</NavLink>
              <NavLink to="/catalog" className={tab}>Products</NavLink>
              <span className="w-px h-5 bg-slate-200 mx-1 self-center" />
              <NavLink to="/pipeline" className={tab}>Pipeline</NavLink>
              <NavLink to="/discount-config" className={tab}>Config</NavLink>
              <NavLink to="/reliability" className={tab}>Audit</NavLink>
            </nav>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <span className="text-xs text-slate-600 font-medium" data-testid="whoami">
              {user?.full_name} · <span className="uppercase text-[10px] font-bold text-slate-500">{user?.role}</span>
            </span>
            <button
              onClick={() => { clearToken("internal"); setAuthed(false); }}
              className="text-xs text-slate-500 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 px-2.5 py-1 rounded-md transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6">
        <Routes>
          <Route index element={<Dashboard />} />
          <Route path="build" element={<QuoteBuilder />} />
          <Route path="quotes" element={<QuoteList />} />
          <Route path="quotes/:id" element={<QuoteBuilder />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="pipeline" element={<Pipeline />} />
          <Route path="fulfillment" element={<FulfillmentList />} />
          <Route path="subscriptions" element={<Subscriptions />} />
          <Route path="invoices" element={<Invoices />} />
          <Route path="catalog" element={<Catalog />} />
          <Route path="discount-config" element={<DiscountConfig />} />
          <Route path="health" element={<HealthDashboard />} />
          <Route path="reports" element={<Reports />} />
          <Route path="reliability" element={<ReliabilityPanel />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
