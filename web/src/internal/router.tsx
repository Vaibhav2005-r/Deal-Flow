/** Internal router tree — rep + manager + finance + admin. */

import { useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { clearToken, hasScope } from "@/lib/auth";
import Approvals from "./Approvals";
import Catalog from "./Catalog";
import Dashboard from "./Dashboard";
import FinanceHome from "./FinanceHome";
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

import { DealFlowLogo } from "@/components/Logo";

function currentUser(): { full_name: string; role: string } | null {
  try {
    const raw = localStorage.getItem("df360.internal.user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

const tab = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 text-xs font-semibold rounded-lg transition-all whitespace-nowrap flex items-center justify-center ${
    isActive
      ? "bg-slate-900 text-white shadow-xs font-semibold"
      : "text-slate-600 hover:text-slate-900 hover:bg-slate-100 font-medium"
  }`;

export default function InternalRouter() {
  const [authed, setAuthed] = useState(hasScope("internal"));
  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  const user = currentUser();
  const isFinance = user?.role?.toLowerCase() === "finance";

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col font-sans">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-2xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          {/* Left: Branding */}
          <div className="flex items-center gap-3 shrink-0">
            <DealFlowLogo size={28} />
          </div>

          {/* Center: Navigation Items */}
          <nav className="flex items-center gap-1 overflow-x-auto no-scrollbar py-1">
            <NavLink to="/" end className={tab}>Home</NavLink>
            
            {!isFinance && <NavLink to="/build" className={tab}>Build</NavLink>}
            
            <NavLink to="/quotes" className={tab}>Quotations</NavLink>
            <NavLink to="/approvals" className={tab}>Approvals</NavLink>
            
            {!isFinance && <NavLink to="/fulfillment" className={tab}>Fulfillment</NavLink>}
            
            <NavLink to="/subscriptions" className={tab}>Subscriptions</NavLink>
            <NavLink to="/invoices" className={tab}>Invoices</NavLink>
            <NavLink to="/health" className={tab}>Deal Health</NavLink>
            <NavLink to="/reports" className={tab}>Reports</NavLink>
            <NavLink to="/catalog" className={tab}>Products</NavLink>
            
            <span className="w-px h-4 bg-slate-200 mx-1 self-center shrink-0" />
            
            {!isFinance && <NavLink to="/pipeline" className={tab}>Pipeline</NavLink>}
            {!isFinance && <NavLink to="/discount-config" className={tab}>Config</NavLink>}
            
            <NavLink to="/reliability" className={tab}>Audit</NavLink>
          </nav>

          {/* Right: User Profile & Sign Out */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="flex items-center gap-2 px-2.5 py-1 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="w-2 h-2 rounded-full bg-[#3b5bf6]" />
              <span className="text-xs font-semibold text-slate-800" data-testid="whoami">
                {user?.full_name ?? "User"}
              </span>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                · {user?.role ?? "Internal"}
              </span>
            </div>
            <button
              onClick={() => { clearToken("internal"); setAuthed(false); }}
              className="text-xs text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-100 border border-slate-200 px-3 py-1.5 rounded-lg transition-colors font-medium shadow-2xs cursor-pointer"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6">
        <Routes>
          <Route index element={isFinance ? <FinanceHome /> : <Dashboard />} />
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
