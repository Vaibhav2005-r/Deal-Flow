/** Internal router tree — Role-based navigation for Finance, Rep, Manager, Admin */

import { useState, useRef, useEffect } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "@/lib/api";
import { clearToken, getCurrentUser, getInternalRole, getRoleDesignation, hasScope, isFinanceUser, type InternalUserInfo } from "@/lib/auth";
import { useMe } from "@/lib/capabilities";
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
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [currentUserData, setCurrentUserData] = useState<InternalUserInfo | null>(() => getCurrentUser());
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Live profile synchronizer with database on mount
  useEffect(() => {
    if (authed) {
      api.get<InternalUserInfo>("/api/auth/me")
        .then((profile) => {
          if (profile && profile.email) {
            setCurrentUserData(profile);
            localStorage.setItem(
              "df360.internal.user",
              JSON.stringify(profile)
            );
          }
        })
        .catch(() => {});
    }
  }, [authed]);

  if (!authed) {
    return (
      <Login
        onLogin={() => {
          setAuthed(true);
          setCurrentUserData(getCurrentUser());
        }}
      />
    );
  }

  const user = currentUserData || getCurrentUser();
  const roleName = user?.role ? String(user.role).toLowerCase() : getInternalRole();
  const isFinance = roleName.includes("finance") || isFinanceUser();

  /**
   * Navigation renders from the capabilities the SERVER grants (§3), not from
   * a role name matched in the client. A rep and a manager differ by more than
   * "is finance", and a UI that decides for itself which role sees which link
   * drifts from what the API actually permits — invisibly, until someone
   * clicks. `can` falls back to the old role check only while /api/me is still
   * in flight, so the first paint is never wrong in the other direction.
   */
  const { can, me } = useMe("internal");
  const ready = !!me;
  const designation = getRoleDesignation(roleName);

  const initials = (user?.full_name ?? "User")
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

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
      <header className="bg-white border-b border-slate-200/90 sticky top-0 z-40 shadow-2xs w-full">
        <div className="w-full px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          {/* Brand */}
          <div className="flex items-center gap-3 shrink-0">
            <DealFlowLogo size={28} />
          </div>

          {/* Center Navigation for Desktop */}
          {/* justify-START, not justify-center. A centred flex row that
              overflows spills equally in BOTH directions, and the left spill
              cannot be reached -- overflow-x-auto has no negative scroll. At
              1280px that put "Home" at x=-59, off-screen and unclickable.
              Dropping flex-1 lets the nav shrink to its content, so mx-auto
              still centres it whenever it fits, which is the common case. */}
          <nav className="hidden md:flex items-center justify-start gap-1 sm:gap-1.5 max-w-4xl mx-auto overflow-x-auto no-scrollbar py-1">
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
            {(ready ? can("view_quotes") : true) && (
              <NavLink to="/quotes" className={tab}>
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span>Quotations</span>
              </NavLink>
            )}

            {/* 3. Approvals */}
            {(ready ? can("view_approvals") : true) && (
              <NavLink to="/approvals" className={tab}>
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Approvals</span>
              </NavLink>
            )}

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
            {(ready ? can("manage_subscriptions") : true) && (
              <NavLink to="/subscriptions" className={tab}>
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                <span>Subscriptions</span>
              </NavLink>
            )}

            {/* 5. Invoices */}
            {(ready ? can("view_invoices") : true) && (
              <NavLink to="/invoices" className={tab}>
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2z" />
                </svg>
                <span>Invoices</span>
              </NavLink>
            )}

            {/* 6. Deal Health */}
            {(ready ? can("view_deal_health") : true) && (
              <NavLink to="/health" className={tab}>
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <span>Deal Health</span>
              </NavLink>
            )}

            {/* 7. Reports */}
            {(ready ? can("view_reports") : true) && (
              <NavLink to="/reports" className={tab}>
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                <span>Reports</span>
              </NavLink>
            )}

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
            {(ready ? can("view_audit_log") : true) && (
              <NavLink to="/reliability" className={tab}>
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                <span>Audit</span>
              </NavLink>
            )}
          </nav>

          {/* Right: Interactive User Profile & Actions */}
          <div className="flex items-center gap-2.5 shrink-0 z-10">
            {/* Clickable User Badge */}
            <div className="relative" ref={userMenuRef}>
              <button
                type="button"
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 hover:border-slate-300 rounded-lg cursor-pointer transition-all shadow-2xs group"
                title="Click to view profile & designation"
              >
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-xs font-semibold text-slate-800 group-hover:text-slate-900" data-testid="whoami">
                  {user?.full_name ?? "User"}
                </span>
                <span
                  className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.2 rounded border ${getRoleBadgeStyle(
                    roleName
                  )}`}
                >
                  {roleName}
                </span>
                <svg
                  className={`w-3.5 h-3.5 text-slate-400 group-hover:text-slate-600 transition-transform duration-200 ${
                    userMenuOpen ? "rotate-180" : ""
                  }`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {/* User Info Popover Modal / Dropdown Card */}
              {userMenuOpen && (
                <div className="absolute right-0 mt-2 w-80 bg-white border border-slate-200 rounded-2xl shadow-xl p-4 z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                  {/* Top Profile Header */}
                  <div className="flex items-start gap-3 pb-3 border-b border-slate-100">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-[#1d72f2] to-blue-600 text-white font-bold flex items-center justify-center text-sm shadow-xs shrink-0">
                      {initials}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-1">
                        <h3 className="text-xs font-bold text-slate-900 truncate">
                          {user?.full_name ?? "User"}
                        </h3>
                        <span
                          className={`text-[9px] font-bold uppercase px-1.5 py-0.2 rounded border ${getRoleBadgeStyle(
                            roleName
                          )}`}
                        >
                          {roleName}
                        </span>
                      </div>
                      <p className="text-[11px] font-semibold text-[#1d72f2] mt-0.5 truncate">
                        {designation}
                      </p>
                    </div>
                  </div>

                  {/* Account Details List */}
                  <div className="py-3 space-y-2.5 text-xs">
                    {/* Official Designation */}
                    <div className="flex items-center gap-2.5 p-2 bg-slate-50 border border-slate-100 rounded-xl">
                      <div className="w-7 h-7 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-slate-500 shrink-0">
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                      </div>
                      <div className="min-w-0 flex-1">
                        <span className="text-[10px] text-slate-400 block font-medium">Designation / Role</span>
                        <span className="font-bold text-slate-800 text-[11px] truncate block">
                          {designation}
                        </span>
                      </div>
                    </div>

                    {/* Workspace & Session Status */}
                    <div className="flex items-center gap-2.5 p-2 bg-slate-50 border border-slate-100 rounded-xl">
                      <div className="w-7 h-7 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-emerald-600 shrink-0">
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                      </div>
                      <div className="min-w-0 flex-1">
                        <span className="text-[10px] text-slate-400 block font-medium">Session Status</span>
                        <span className="font-bold text-emerald-700 text-[11px] flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          Active & Verified Session
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="pt-2 border-t border-slate-100 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        clearToken("internal");
                        setAuthed(false);
                      }}
                      className="w-full py-2 px-3 bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 rounded-xl text-xs font-semibold transition-colors flex items-center justify-center gap-1.5 cursor-pointer shadow-2xs"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                      </svg>
                      <span>Sign Out</span>
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Mobile Menu Toggle Button */}
            <button
              type="button"
              onClick={() => setMobileNavOpen(!mobileNavOpen)}
              className="md:hidden p-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 border border-slate-200"
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
          <div className="md:hidden border-t border-slate-200 bg-white px-4 py-3 shadow-lg space-y-1">
            <div className="sm:hidden flex items-center justify-between pb-2 mb-2 border-b border-slate-100">
              <div>
                <span className="text-xs font-semibold text-slate-800 block">{user?.full_name ?? "User"}</span>
                <span className="text-[10px] text-[#1d72f2] font-medium block">{designation}</span>
              </div>
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
              {(ready ? can("build_quote") : !isFinance) && <NavLink to="/build" className={tab}>Build Quote</NavLink>}
              {(ready ? can("view_quotes") : true) && <NavLink to="/quotes" className={tab}>Quotations</NavLink>}
              {(ready ? can("view_approvals") : true) && <NavLink to="/approvals" className={tab}>Approvals</NavLink>}
              {(ready ? can("view_fulfillment") : !isFinance) && <NavLink to="/fulfillment" className={tab}>Fulfillment</NavLink>}
              {(ready ? can("manage_subscriptions") : true) && <NavLink to="/subscriptions" className={tab}>Subscriptions</NavLink>}
              {(ready ? can("view_invoices") : true) && <NavLink to="/invoices" className={tab}>Invoices</NavLink>}
              {(ready ? can("view_deal_health") : true) && <NavLink to="/health" className={tab}>Deal Health</NavLink>}
              {(ready ? can("view_reports") : true) && <NavLink to="/reports" className={tab}>Reports</NavLink>}
              {(ready ? can("manage_catalog") : !isFinance) && <NavLink to="/catalog" className={tab}>Products</NavLink>}
              {(ready ? can("view_fulfillment") : !isFinance) && <NavLink to="/pipeline" className={tab}>Pipeline</NavLink>}
              {(ready ? can("configure_discounts") : !isFinance) && <NavLink to="/discount-config" className={tab}>Config</NavLink>}
              {(ready ? can("view_audit_log") : true) && <NavLink to="/reliability" className={tab}>Audit</NavLink>}
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
