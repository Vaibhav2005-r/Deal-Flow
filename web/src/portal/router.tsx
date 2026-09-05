/**
 * Customer portal router tree — SEPARATE from the internal tree.
 *
 * Spec §1 constraint 2 / §13: this is not the internal screen with a flag.
 * It has its own auth scope ("portal"), its own routes, and its own
 * components; it never imports from src/internal.
 */

import { Navigate, Route, Routes } from "react-router-dom";
import { hasScope } from "@/lib/auth";

function RequirePortal({ children }: { children: JSX.Element }) {
  return hasScope("portal") ? children : <Navigate to="/portal/login" replace />;
}

const Placeholder = ({ name }: { name: string }) => (
  <section>
    <h2>{name}</h2>
    <p>Phase 5 — the loop.</p>
  </section>
);

export default function PortalRouter() {
  return (
    <RequirePortal>
      <Routes>
        <Route index element={<Placeholder name="Your quotations" />} />
        <Route path="quotes/:id" element={<Placeholder name="Review & counter" />} />
      </Routes>
    </RequirePortal>
  );
}
