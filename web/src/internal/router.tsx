/** Internal router tree — Role-based navigation for Finance, Rep, Manager, Admin */

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

// Enterprise tab styling with icon and typography
const tab = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 text-xs font-semibold rounded-lg transition-all whitespace-nowrap flex items-center gap-1.5 cursor-pointer ${
    isActive
      ? "bg-slate-900 text-white shadow-xs"
      : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
  }`;

export default function InternalRouter() {
  const [authed, setAuthed] = useState(hasScope("internal"));
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  const user = currentUser();
  const roleName = (user?.role ?? "internal").toLowerCase();
  const isFinance = roleName === "finance";

  const getRoleBadgeStyle = (r: string) => {
    switch (r) {
      case "finance":
        return "bg-emerald-50 text-emerald-700 border-emerald-200";
      case "manager":
        return "bg-purple-50 text-purple-700 border-purple-200";
      case "rep":
        return "bg-blue-50 text-blue-700 border-blue-200";
      default:
        return "bg-slate-100 text-slate-700 border-slate-200";
    }
  };

  return (
    <div className="min-h-screen bg-[#f8fafc] text-slate-900 flex flex-col font-sans antialiased">
      {/* Top Enterprise Header */}
      <header className="bg-white border-b border-slate-200/90 sticky top-0 z-40 shadow-2xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-3">
          {/* Brand */}
          <div className="flex items-center gap-3 shrink-0">
            <DealFlowLogo size={28} />
          </div>

          {/* Center Navigation for Desktop */}
          <nav className="hidden lg:flex items-center gap-1 overflow-x-auto no-scrollbar py-1">
            {/* 1. Home (FinanceHome for Finance, Dashboard for Rep/Manager) */}
            <NavLink to="/" end className={tab}>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
              </svg>
              <span>Home</span>
            </NavLink>

            {/* Non-Finance Only: Build Quote */}
            {!isFinance && (
              <NavLink to="/build" className={tab}>
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                </svg>
                <span>Build Quote</span>
              </NavLink>
            )}

            {/* 2. Quotations */}
            <NavLink to="/quotes" className={tab}>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>Quotations</span>
            </NavLink>

            {/* 3. Approvals */}
            <NavLink to="/approvals" className={tab}>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Approvals</span>
            </NavLink>

            {/* Non-Finance Only: Fulfillment */}
            {!isFinance && (
              <NavLink to="/fulfillment" className={tab}>
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                </svg>
                <span>Fulfillment</span>
              </NavLink>
            )}

            {/* 4. Subscriptions */}
            <NavLink to="/subscriptions" className={tab}>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <span>Subscriptions</span>
            </NavLink>

            {/* 5. Invoices */}
            <NavLink to="/invoices" className={tab}>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2z" />
              </svg>
              <span>Invoices</span>
            </NavLink>

            {/* 6. Deal Health */}
            <NavLink to="/health" className={tab}>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <span>Deal Health</span>
            </NavLink>

            {/* 7. Reports */}
            <NavLink to="/reports" className={tab}>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              <span>Reports</span>
            </NavLink>

            {/* Non-Finance Only: Products/Catalog, Pipeline, Config */}
            {!isFinance && (
              <>
                <NavLink to="/catalog" className={tab}>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                  <span>Products</span>
                </NavLink>
                <span className="w-px h-4 bg-slate-200 mx-1 self-center shrink-0" />
                <NavLink to="/pipeline" className={tab}>
                  <span>Pipeline</span>
                </NavLink>
                <NavLink to="/discount-config" className={tab}>
                  <span>Config</span>
                </NavLink>
              </>
            )}

            {/* 8. Audit */}
            <NavLink to="/reliability" className={tab}>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              <span>Audit</span>
            </NavLink>
          </nav>

          {/* Right: User Profile & Actions */}
          <div className="flex items-center gap-2.5 shrink-0">
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs font-semibold text-slate-800" data-testid="whoami">
                {user?.full_name ?? "User"}
              </span>
              <span
                className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.2 rounded border ${getRoleBadgeStyle(
                  roleName
                )}`}
              >
                {roleName}
              </span>
            </div>

            <button
              type="button"
              onClick={() => {
                clearToken("internal");
                setAuthed(false);
              }}
              className="text-xs font-semibold text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-100 border border-slate-200 px-3 py-1.5 rounded-lg transition-colors shadow-2xs cursor-pointer"
              title="Sign out of your account"
            >
              Sign out
            </button>

            {/* Mobile Menu Toggle Button */}
            <button
              type="button"
              onClick={() => setMobileNavOpen(!mobileNavOpen)}
              className="lg:hidden p-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 border border-slate-200"
              aria-label="Toggle Navigation"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                {mobileNavOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
          </div>
        </div>

        {/* Mobile Nav Drawer */}
        {mobileNavOpen && (
          <div className="lg:hidden border-t border-slate-200 bg-white px-4 py-3 shadow-lg space-y-1">
            <div className="sm:hidden flex items-center justify-between pb-2 mb-2 border-b border-slate-100">
              <span className="text-xs font-semibold text-slate-800">{user?.full_name ?? "User"}</span>
              <span
                className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.2 rounded border ${getRoleBadgeStyle(
                  roleName
                )}`}
              >
                {roleName}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-1" onClick={() => setMobileNavOpen(false)}>
              <NavLink to="/" end className={tab}>Home</NavLink>
              {!isFinance && <NavLink to="/build" className={tab}>Build Quote</NavLink>}
              <NavLink to="/quotes" className={tab}>Quotations</NavLink>
              <NavLink to="/approvals" className={tab}>Approvals</NavLink>
              {!isFinance && <NavLink to="/fulfillment" className={tab}>Fulfillment</NavLink>}
              <NavLink to="/subscriptions" className={tab}>Subscriptions</NavLink>
              <NavLink to="/invoices" className={tab}>Invoices</NavLink>
              <NavLink to="/health" className={tab}>Deal Health</NavLink>
              <NavLink to="/reports" className={tab}>Reports</NavLink>
              {!isFinance && <NavLink to="/catalog" className={tab}>Products</NavLink>}
              {!isFinance && <NavLink to="/pipeline" className={tab}>Pipeline</NavLink>}
              {!isFinance && <NavLink to="/discount-config" className={tab}>Config</NavLink>}
              <NavLink to="/reliability" className={tab}>Audit</NavLink>
            </div>
          </div>
        )}
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1">
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
