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
import PortalLogin from "./PortalLogin";
import QuoteList from "./QuoteList";
import QuoteDetail from "./QuoteDetail";

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
            <QuoteDetail />
          </RequirePortal>
        }
      />
      <Route
        path="*"
        element={
          <RequirePortal>
            <QuoteList />
          </RequirePortal>
        }
      />
    </Routes>
  );
}
