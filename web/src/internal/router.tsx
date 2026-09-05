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
  `px-3 py-1.5 text-xs font-semibold rounded-lg transition-all whitespace-nowrap flex items-center gap-1.5 ${
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
            <NavLink to="/" end className={tab}>
              <span>Home</span>
            </NavLink>

            {!isFinance && (
              <NavLink to="/build" className={tab}>
                <span>Build Quote</span>
              </NavLink>
            )}

            <NavLink to="/quotes" className={tab}>
              <span>Quotations</span>
            </NavLink>
            <NavLink to="/approvals" className={tab}>
              <span>Approvals</span>
            </NavLink>

            {!isFinance && (
              <NavLink to="/fulfillment" className={tab}>
                <span>Fulfillment</span>
              </NavLink>
            )}

            <NavLink to="/subscriptions" className={tab}>
              <span>Subscriptions</span>
            </NavLink>
            <NavLink to="/invoices" className={tab}>
              <span>Invoices</span>
            </NavLink>
            <NavLink to="/health" className={tab}>
              <span>Deal Health</span>
            </NavLink>
            <NavLink to="/reports" className={tab}>
              <span>Reports</span>
            </NavLink>
            <NavLink to="/catalog" className={tab}>
              <span>Products</span>
            </NavLink>

            <span className="w-px h-4 bg-slate-200 mx-1 self-center shrink-0" />

            {!isFinance && (
              <NavLink to="/pipeline" className={tab}>
                <span>Pipeline</span>
              </NavLink>
            )}
            {!isFinance && (
              <NavLink to="/discount-config" className={tab}>
                <span>Config</span>
              </NavLink>
            )}

            <NavLink to="/reliability" className={tab}>
              <span>Audit</span>
            </NavLink>
          </nav>

          {/* Right: User Profile & Actions */}
          <div className="flex items-center gap-2.5 shrink-0">
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs font-semibold text-slate-800" data-testid="whoami">
                {user?.full_name ?? "Enterprise User"}
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
              <NavLink to="/catalog" className={tab}>Products</NavLink>
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
