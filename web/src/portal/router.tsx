/**
 * Customer portal router tree — SEPARATE from the internal tree.
 *
 * Spec §1 constraint 2 / §13: this is not the internal screen with a flag.
 * It has its own auth scope ("portal"), its own routes, and its own
 * components; it never imports from src/internal.
 */

import { useState, useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { hasScope } from "@/lib/auth";
import { NavLink } from "react-router-dom";
import { clearToken } from "@/lib/auth";
import { useMe } from "@/lib/capabilities";
import PortalLogin from "./PortalLogin";
import QuoteList from "./QuoteList";
import QuoteDetail from "./QuoteDetail";
import Messages from "./Messages";
import Profile from "./Profile";

const portalTab = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 text-sm rounded-lg font-medium ${
    isActive ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-100"
  }`;

/**
 * Portal chrome: My Quotations | Messages | Profile (product flow screen 11).
 *
 * Tabs render from the capabilities the SERVER grants this account, not from a
 * hardcoded list, so the portal and the API cannot disagree about what a
 * customer may reach.
 */
function PortalShell({ children }: { children: JSX.Element }) {
  const { me, can } = useMe("portal");

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2 shrink-0">
            <span className="w-7 h-7 rounded-lg bg-indigo-600 text-white text-xs font-bold grid place-items-center">
              DF
            </span>
            <div className="leading-tight">
              <p className="text-sm font-semibold text-slate-900">DealFlow360</p>
              <p className="text-[11px] text-slate-500">Customer Portal</p>
            </div>
          </div>

          <nav className="flex gap-1 ml-4">
            {can("portal_view_quotes") && (
              <NavLink to="/portal" end className={portalTab}>My Quotations</NavLink>
            )}
            {can("portal_negotiate") && (
              <NavLink to="/portal/messages" className={portalTab}>Messages</NavLink>
            )}
            {can("portal_view_profile") && (
              <NavLink to="/portal/profile" className={portalTab}>Profile</NavLink>
            )}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <span className="text-sm text-slate-600 hidden sm:block" data-testid="portal-whoami">
              {me?.customer?.name ?? me?.full_name ?? ""}
            </span>
            <button
              onClick={() => {
                clearToken("portal");
                localStorage.removeItem("df360.portal.user");
                window.location.assign("/portal/login");
              }}
              className="text-sm text-slate-500 hover:text-slate-900"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-6">{children}</main>
    </div>
  );
}

function RequirePortal({ children }: { children: JSX.Element }) {
  return hasScope("portal") ? children : <Navigate to="/portal/login" replace />;
}

export default function PortalRouter() {
  const [, setAuthed] = useState(() => hasScope("portal"));
  const navigate = useNavigate();

  useEffect(() => {
    const handleStorage = () => setAuthed(hasScope("portal"));
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  return (
    <Routes>
      <Route
        path="login"
        element={
          <PortalLogin
            onLogin={() => {
              setAuthed(true);
              navigate("/portal", { replace: true });
            }}
          />
        }
      />
      <Route
        path="quotes/:id"
        element={
          <RequirePortal>
              <PortalShell><QuoteDetail /></PortalShell>
            </RequirePortal>
        }
      />
      <Route
        path="messages"
        element={
          <RequirePortal>
            <PortalShell><Messages /></PortalShell>
          </RequirePortal>
        }
      />
      <Route
        path="profile"
        element={
          <RequirePortal>
            <PortalShell><Profile /></PortalShell>
          </RequirePortal>
        }
      />
      <Route
        path="*"
        element={
          <RequirePortal>
              <PortalShell><QuoteList /></PortalShell>
            </RequirePortal>
        }
      />
    </Routes>
  );
}
