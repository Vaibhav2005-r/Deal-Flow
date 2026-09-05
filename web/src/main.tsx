import React from "react";
import "@/index.css";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import InternalRouter from "@/internal/router";
import PortalRouter from "@/portal/router";

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* two separate trees, two separate auth scopes (§1) */}
          <Route path="/portal/*" element={<PortalRouter />} />
          <Route path="/*" element={<InternalRouter />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
