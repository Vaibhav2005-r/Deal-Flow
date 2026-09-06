"""The verified control -> endpoint map.

Written by hand from the resolver output plus a read of each handler, because
the automated pass cannot follow a path built from a variable
(`/api/quotes/${selected}${path}`) or a submit button to its form's onSubmit.
Every entry here was checked against the source.

Screen -> list of (control label, kind, endpoint or note)
  endpoint "" means the control issues no request of its own.
"""

NAV = "nav"          # routes to another screen; that screen's own loads apply
UI = "ui"            # client-side only: toggles, modals, pagination, tabs
CALL = "call"        # issues an HTTP request

SCREENS: list[dict] = [
 {
  "screen": "Sign in  (/login)",
  "file": "web/src/internal/Login.tsx",
  "loads": ["GET /api/auth/demo-accounts"],
  "controls": [
   ("Sign In (submit)", CALL, ["POST /api/auth/login"],
    "Reads the account, then the app calls GET /api/me for capabilities."),
   ("Create Account (submit, Create tab)", CALL, ["POST /api/auth/register"],
    "Always creates a rep; the requested role is ignored."),
   ("Sales Rep / Manager / Finance / Admin / Customer", CALL,
    ["GET /api/auth/demo-accounts", "POST /api/auth/login"],
    "Demo buttons. Credentials come from the server, then the ordinary login."),
   ("Create Account / Sign In (tab switch)", UI, [], "Switches form mode."),
   ("Show / hide password", UI, [], ""),
   ("Forgot password?", UI, [], "Shows a notice; no request."),
   ("Customer Portal", NAV, [], "Links to /portal/login."),
  ],
 },
 {
  "screen": "Customer portal sign in  (/portal/login)",
  "file": "web/src/portal/PortalLogin.tsx",
  "loads": [],
  "controls": [
   ("Sign In to Customer Portal (submit)", CALL, ["POST /api/auth/login"],
    "Rejected unless the account's scope is portal."),
   ("Create Customer Account (submit)", CALL, ["POST /api/auth/portal-signup"],
    "Creates the login and its customer record together."),
   ("Sign In / Sign Up (tab switch)", UI, [], ""),
   ("Show / hide password", UI, [], ""),
   ("Switch to Internal Employee Console", NAV, [], "Links to /login."),
  ],
 },
 {
  "screen": "Home — rep & manager  (/)",
  "file": "web/src/internal/Dashboard.tsx",
  "loads": ["GET /api/dashboard"],
  "controls": [
   ("+ New Quotation", NAV, [], "Opens /build."),
   ("View Approvals", NAV, [], "Opens /approvals. Hidden without view_approvals."),
   ("At-risk deal row", NAV, [], "Opens /health."),
  ],
 },
 {
  "screen": "Home — finance  (/)",
  "file": "web/src/internal/FinanceHome.tsx",
  "loads": ["GET /api/dashboard", "GET /api/reports/revenue-trend",
            "GET /api/invoices", "GET /api/approvals", "GET /api/subscriptions",
            "GET /api/deal-health", "GET /api/quotes"],
  "controls": [
   ("Refresh", CALL, ["GET /api/invoices", "GET /api/approvals",
                      "GET /api/subscriptions", "GET /api/deal-health",
                      "GET /api/quotes"], "Re-runs every load on the screen."),
   ("Monthly / Quarterly / Yearly", CALL, ["GET /api/reports/revenue-trend"],
    "Re-queries the trend for that period."),
   ("Review  ·  View all  ·  Inspect", NAV, [], "Open /approvals, /invoices, /health."),
   ("Review Approvals / Ledger Invoices / Revenue Reports / Audit Registry", NAV, [],
    "Shortcut tiles to /approvals, /invoices, /reports, /reliability."),
  ],
 },
 {
  "screen": "Build Quote  (/build)",
  "file": "web/src/internal/QuoteBuilder.tsx",
  "loads": ["GET /api/customers", "GET /api/products", "GET /api/discount-policies",
            "GET /api/quotes/{id}", "GET /api/quotes/{id}/messages",
            "GET /api/quotes/{id}/suggestions"],
  "controls": [
   ("Create quote", CALL, ["POST /api/quotes"], "Opens a DRAFT for the chosen customer."),
   ("Start another", UI, [], "Clears the form; no request."),
   ("Add line", CALL, ["POST /api/quotes/{id}/lines"],
    "The sanctioned mutation path: re-scores and voids live approvals."),
   ("Delete (line row)", CALL, ["DELETE /api/quotes/{id}/lines/{line_id}"], ""),
   ("Apply to all lines", CALL, ["POST /api/quotes/{id}/order-discount"],
    "Sets one discount across every line, then re-scores."),
   ("Confirm & score", CALL, ["POST /api/quotes/{id}/confirm"],
    "Runs BDRS and routes to the approval chain."),
   ("Send to Customer Portal", CALL, ["POST /api/quotes/{id}/send-to-portal"], ""),
   ("Accept Counter-Offer", CALL, ["POST /api/quotes/{id}/accept-counter"],
    "Applies the customer's counter as a line edit and re-scores."),
   ("Send Reply (submit)", CALL, ["POST /api/quotes/{id}/messages"], ""),
   ("Add to quote (upsell)", CALL, ["POST /api/quotes/{id}/lines"],
    "Same path as Add line."),
   ("Dismiss (upsell)", UI, [], "Hides the suggestion for this session."),
   ("View all quotes", NAV, [], "Opens /quotes."),
  ],
 },
 {
  "screen": "Quotations  (/quotes)",
  "file": "web/src/internal/QuoteList.tsx",
  "loads": ["GET /api/quotes"],
  "controls": [
   ("Showing assigned / all accounts", CALL, ["GET /api/quotes"], "Re-queries with all_quotes."),
   ("Board / table view", UI, [], ""),
   ("Search, clear search", CALL, ["GET /api/quotes"], "Server-side filter."),
   ("Quote card / Review", NAV, [], "Opens /quotes/{id}."),
   ("Prev / Next / page number", CALL, ["GET /api/quotes"], "Server-side paging."),
  ],
 },
 {
  "screen": "Approvals  (/approvals)",
  "file": "web/src/internal/Approvals.tsx",
  "loads": ["GET /api/approvals"],
  "controls": [
   ("Approve Quotation", CALL, ["POST /api/quotes/{quote_id}/approve"],
    "Advances the chain; may transition the quote to APPROVED."),
   ("Return for Revision", CALL, ["POST /api/quotes/{quote_id}/return"],
    "Requires a reason; sends the quote back to DRAFT."),
   ("Reject Quotation", CALL, ["POST /api/quotes/{quote_id}/reject"], "Requires a reason."),
   ("Review Breakdown", UI, [], "Expands the row; data already loaded."),
   ("Pending / Returned / Approved tabs", CALL, ["GET /api/approvals"], ""),
   ("Prev / Next", CALL, ["GET /api/approvals"], ""),
  ],
 },
 {
  "screen": "Fulfillment  (/fulfillment)",
  "file": "web/src/internal/FulfillmentList.tsx",
  "loads": ["GET /api/warehouses", "GET /api/fulfillment/pending",
            "GET /api/fulfillment/stock"],
  "controls": [
   ("Warehouse filter", CALL, ["GET /api/fulfillment/stock"], ""),
   ("Order row / Manage Split", NAV, [], "Opens /pipeline for that quote."),
   ("Prev / Next", CALL, ["GET /api/fulfillment/pending", "GET /api/fulfillment/stock"], ""),
  ],
 },
 {
  "screen": "Pipeline  (/pipeline)",
  "file": "web/src/internal/Pipeline.tsx",
  "loads": ["GET /api/quotes", "GET /api/quotes/{id}", "GET /api/quotes/{id}/fulfillment",
            "GET /api/quotes/{id}/invoices", "GET /api/quotes/{id}/amount-due",
            "GET /api/quotes/{id}/billing-detail", "GET /api/fulfillment/stock"],
  "controls": [
   ("1. Send to portal", CALL, ["POST /api/quotes/{quote_id}/send-to-portal"], ""),
   ("2. Customer confirm", CALL, ["POST /api/quotes/{quote_id}/customer-confirm"], ""),
   ("Accept customer counter", CALL, ["POST /api/quotes/{quote_id}/accept-counter"], ""),
   ("3. Plan fulfillment", CALL, ["POST /api/quotes/{quote_id}/plan-fulfillment"],
    "Allocates stock and reserves it."),
   ("4. Generate invoices", CALL, ["POST /api/quotes/{quote_id}/generate-invoices"], ""),
   ("5. Record payment", CALL, ["POST /api/quotes/{quote_id}/payments"], ""),
   ("Check Inbound Consolidation", CALL,
    ["POST /api/quotes/{quote_id}/fulfillment/consolidate/{product_id}"], ""),
   ("Manual Override Split / Cancel", UI, [], "Opens the override editor."),
   ("Apply Override & Recalculate Split", CALL,
    ["POST /api/quotes/{quote_id}/fulfillment/override"],
    "Re-reserves stock against the chosen warehouses."),
   ("Pause / Resume subscription", CALL, ["POST /api/quotes/{quote_id}/subscription/pause"], ""),
   ("Cancel subscription", CALL, ["POST /api/quotes/{quote_id}/subscription/cancel"],
    "Prompts for a reason."),
  ],
 },
 {
  "screen": "Subscriptions  (/subscriptions)",
  "file": "web/src/internal/Subscriptions.tsx",
  "loads": ["GET /api/subscriptions"],
  "controls": [
   ("All / Active / Paused / Cancelled", CALL, ["GET /api/subscriptions"], ""),
   ("Prev / Next / page size", CALL, ["GET /api/subscriptions"], ""),
  ],
 },
 {
  "screen": "Invoices  (/invoices)",
  "file": "web/src/internal/Invoices.tsx",
  "loads": ["GET /api/invoices/summary", "GET /api/invoices"],
  "controls": [
   ("Inspect", CALL, ["GET /api/invoices/{invoice_id}"], "Loads lines, credits and payments."),
   ("All / Unpaid / Paid", CALL, ["GET /api/invoices", "GET /api/invoices/summary"], ""),
   ("Search", CALL, ["GET /api/invoices"], ""),
   ("Close Detail", UI, [], ""),
   ("Prev / Next", CALL, ["GET /api/invoices"], ""),
  ],
 },
 {
  "screen": "Deal Health  (/health)",
  "file": "web/src/internal/HealthDashboard.tsx",
  "loads": ["GET /api/deal-health"],
  "controls": [
   ("Refresh", CALL, ["GET /api/deal-health"], ""),
   ("Filter Alerts Only", UI, [], "Client-side filter over loaded rows."),
   ("Inspect / Close", UI, [], "Opens the detail drawer."),
   ("Go to Quote", NAV, [], "Opens /quotes/{id}."),
   ("Prev / Next", CALL, ["GET /api/deal-health"], ""),
  ],
 },
 {
  "screen": "Reports  (/reports)",
  "file": "web/src/internal/Reports.tsx",
  "loads": ["GET /api/reports"],
  "controls": [
   ("Period / rep / state / category filters", CALL, ["GET /api/reports"], ""),
   ("Export CSV", CALL, ["GET /api/reports/export"], "Streams a file; writes nothing."),
   ("Export Excel (.xls)", CALL, ["GET /api/reports/export"], ""),
  ],
 },
 {
  "screen": "Products  (/catalog)",
  "file": "web/src/internal/Catalog.tsx",
  "loads": ["GET /api/catalog/summary", "GET /api/catalog/products"],
  "controls": [
   ("+ New Product / Cancel", UI, [], "Opens the create form."),
   ("Save Product (submit)", CALL, ["POST /api/catalog/products"], ""),
   ("Inspect", CALL, ["GET /api/catalog/products/{product_id}"],
    "Loads variants and per-price-list prices."),
   ("Category filter / search", CALL, ["GET /api/catalog/products"], ""),
   ("Close", UI, [], ""),
   ("Prev / Next", CALL, ["GET /api/catalog/products"], ""),
  ],
 },
 {
  "screen": "Config  (/discount-config)",
  "file": "web/src/internal/DiscountConfig.tsx",
  "loads": ["GET /api/admin/discount-config"],
  "controls": [
   ("Save configuration", CALL, ["PUT /api/admin/discount-config"],
    "Validated first: unknown tier/category or a category above its tier cap is refused."),
  ],
 },
 {
  "screen": "Ops  (/operations)",
  "file": "web/src/internal/Operations.tsx",
  "loads": ["GET /api/admin/warehouses", "GET /api/admin/subscription-plans"],
  "controls": [
   ("Add warehouse", CALL, ["POST /api/admin/warehouses"], ""),
   ("Add plan", CALL, ["POST /api/admin/subscription-plans"], ""),
  ],
 },
 {
  "screen": "Audit  (/reliability)",
  "file": "web/src/internal/ReliabilityPanel.tsx",
  "loads": ["GET /api/reliability/stats", "GET /api/reliability/logs"],
  "controls": [
   ("Refresh Log", CALL, ["GET /api/reliability/logs"], ""),
   ("Replay", CALL, ["POST /api/reliability/replay/{log_id}"],
    "Re-runs the recorded call and compares; appends nothing."),
   ("Agent / verdict filters", CALL, ["GET /api/reliability/logs"], ""),
   ("Done / close", UI, [], ""),
  ],
 },
 {
  "screen": "Portal — My Quotations  (/portal)",
  "file": "web/src/portal/QuoteList.tsx",
  "loads": ["GET /api/portal/quotes"],
  "controls": [
   ("Refresh", CALL, ["GET /api/portal/quotes"], ""),
   ("Review & Negotiate", NAV, [], "Opens /portal/quotes/{id}."),
   ("Prev / Next / per page", CALL, ["GET /api/portal/quotes"], ""),
  ],
 },
 {
  "screen": "Portal — Quotation detail  (/portal/quotes/{id})",
  "file": "web/src/portal/QuoteDetail.tsx",
  "loads": ["GET /api/portal/quotes/{quote_id}", "GET /api/portal/quotes/{quote_id}/messages"],
  "controls": [
   ("Submit Request", CALL, ["POST /api/portal/quotes/{quote_id}/counter"],
    "Records the counter-offer; a rep must accept it before any line changes."),
   ("Confirm Quotation", CALL, ["POST /api/portal/quotes/{quote_id}/confirm"], ""),
   ("Send Reply (submit)", CALL, ["POST /api/portal/quotes/{quote_id}/messages"], ""),
   ("Dismiss banner", UI, [], ""),
  ],
 },
 {
  "screen": "Portal — Messages  (/portal/messages)",
  "file": "web/src/portal/Messages.tsx",
  "loads": ["GET /api/portal/messages"],
  "controls": [("Quotation link", NAV, [], "Opens that quotation in the portal.")],
 },
 {
  "screen": "Portal — Profile  (/portal/profile)",
  "file": "web/src/portal/Profile.tsx",
  "loads": ["GET /api/portal/profile"],
  "controls": [],
 },
 {
  "screen": "Shell — top navigation (both apps)",
  "file": "web/src/internal/router.tsx, web/src/portal/router.tsx",
  "loads": ["GET /api/me"],
  "controls": [
   ("Home, Build Quote, Quotations, Approvals, Fulfillment, Subscriptions, "
    "Invoices, Deal Health, Reports, Products, Pipeline, Config, Ops, Audit",
    NAV, [], "Each link is shown only if GET /api/me grants its capability."),
   ("My Quotations, Messages, Profile (portal)", NAV, [], "Same, from the portal capabilities."),
   ("Reload data", UI, [], "Reloads the page."),
   ("Sign Out", UI, [], "Clears the token locally; no request."),
   ("User menu, mobile menu", UI, [], ""),
  ],
 },
]
