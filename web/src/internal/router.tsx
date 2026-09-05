/** Internal router tree — rep + manager + finance + admin. */

import { Navigate, Route, Routes } from "react-router-dom";
import { hasScope } from "@/lib/auth";

function RequireInternal({ children }: { children: JSX.Element }) {
  return hasScope("internal") ? children : <Navigate to="/login" replace />;
}

const Placeholder = ({ name }: { name: string }) => (
  <section>
    <h2>{name}</h2>
    <p>Phase 3 — the spine.</p>
  </section>
);

export default function InternalRouter() {
  return (
    <RequireInternal>
      <Routes>
        <Route index element={<Placeholder name="Quotes" />} />
        <Route path="quotes/:id" element={<Placeholder name="Quote builder" />} />
        <Route path="approvals" element={<Placeholder name="Approvals" />} />
        <Route path="fulfillment" element={<Placeholder name="Fulfillment" />} />
        <Route path="billing" element={<Placeholder name="Billing" />} />
        <Route path="reliability" element={<Placeholder name="Decision log" />} />
      </Routes>
    </RequireInternal>
  );
}
