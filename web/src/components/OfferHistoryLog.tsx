import type { PortalMessage, Line, PortalLine } from "@/lib/api";

export interface OfferLogItem {
  round: number;
  type: "INITIAL_OFFER" | "CUSTOMER_COUNTER" | "REP_COUNTER" | "ACCEPTED" | "NOTE";
  party: "Sales Representative" | "Customer" | "System";
  isCustomer: boolean;
  authorName: string;
  authorRole?: string | null;
  discountPct?: number | null;
  deliveryDate?: string | null;
  lineId?: number | null;
  productName?: string | null;
  netTotal?: number | string | null;
  body: string;
  timestamp: string;
}

interface OfferHistoryLogProps {
  quoteId: number;
  quoteVersion?: number;
  quoteState: string;
  lines?: (Line | PortalLine)[];
  messages: PortalMessage[];
  customerName?: string;
  repName?: string;
  netTotal?: number | string;
  isInternal?: boolean;
  onMakeCounterOffer?: () => void;
  onReviseTerms?: () => void;
  onAcceptCounter?: () => void;
  latestCustomerCounterPct?: number | null;
}

function formatCurrency(val: number | string | null | undefined): string {
  if (val === null || val === undefined) return "—";
  const num = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(num)) return String(val);
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(num);
}

export default function OfferHistoryLog({
  quoteId,
  quoteVersion = 1,
  quoteState,
  lines = [],
  messages,
  customerName,
  repName,
  netTotal,
  isInternal = true,
  onMakeCounterOffer,
  onReviseTerms,
  onAcceptCounter,
  latestCustomerCounterPct,
}: OfferHistoryLogProps) {
  // Build chronological negotiation rounds
  const rounds: OfferLogItem[] = [];

  // Round 1: Initial Offer by Sales Rep
  rounds.push({
    round: 1,
    type: "INITIAL_OFFER",
    party: "Sales Representative",
    isCustomer: false,
    authorName: repName || "Sales Representative",
    authorRole: "REP",
    body: `Initial quotation proposal (v1) created and prepared with ${lines.length} line item${lines.length === 1 ? "" : "s"}.`,
    netTotal: netTotal,
    timestamp: messages.length > 0 ? messages[0].created_at : new Date().toISOString(),
  });

  // Track rounds from messages
  let currentRound = 1;

  messages.forEach((msg) => {
    const isCust =
      msg.is_customer === true ||
      msg.author_role === "PORTAL" ||
      msg.author_name.toLowerCase().includes("customer") ||
      (customerName && msg.author_name.toLowerCase().includes(customerName.toLowerCase()));

    const targetLine = msg.quote_line_id
      ? lines.find((l) => l.id === msg.quote_line_id)
      : null;

    // Extract requested delivery date from body if formatted like [Delivery: 2026-10-15]
    let deliveryDate: string | null = null;
    const dateMatch = msg.body.match(/\[Delivery:\s*([0-9\-]+)\]/i);
    if (dateMatch) {
      deliveryDate = dateMatch[1];
    } else {
      const dateTextMatch = msg.body.match(/Requested Delivery Date:\s*([0-9\-]+)/i);
      if (dateTextMatch) {
        deliveryDate = dateTextMatch[1];
      }
    }

    const discount = msg.counter_discount_pct !== null ? parseFloat(msg.counter_discount_pct) : null;
    const isCounter = discount !== null || !!deliveryDate || msg.body.toLowerCase().includes("counter");

    currentRound += 1;

    let type: OfferLogItem["type"] = "NOTE";
    if (isCounter) {
      type = isCust ? "CUSTOMER_COUNTER" : "REP_COUNTER";
    }

    rounds.push({
      round: currentRound,
      type,
      party: isCust ? "Customer" : "Sales Representative",
      isCustomer: Boolean(isCust),
      authorName: msg.author_name,
      authorRole: msg.author_role,
      discountPct: discount,
      deliveryDate,
      lineId: msg.quote_line_id,
      productName: targetLine ? targetLine.product_name : undefined,
      body: msg.body.replace(/\[Delivery:\s*[0-9\-]+\]\s*/i, ""),
      timestamp: msg.created_at,
    });
  });

  // Check if quote was confirmed
  if (quoteState === "CONFIRMED" || quoteState === "FULFILLING" || quoteState === "PAID") {
    currentRound += 1;
    rounds.push({
      round: currentRound,
      type: "ACCEPTED",
      party: "Customer",
      isCustomer: true,
      authorName: customerName || "Customer Authorized Contact",
      body: "Final terms and commercial proposal accepted and confirmed. Order released for fulfillment.",
      netTotal: netTotal,
      timestamp: new Date().toISOString(),
    });
  }

  const containerBg = isInternal
    ? "bg-white border-slate-200 text-slate-800"
    : "bg-[#111827] border-slate-800 text-slate-100";
  const headerBg = isInternal ? "border-slate-100" : "border-slate-800";
  const subtextCol = isInternal ? "text-slate-500" : "text-slate-400";

  return (
    <div className={`border rounded-2xl p-5 sm:p-6 shadow-sm space-y-5 ${containerBg}`} data-testid="offer-history-log">
      {/* Header */}
      <div className={`flex flex-wrap items-center justify-between gap-3 border-b pb-4 ${headerBg}`}>
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-purple-600/10 text-purple-600 font-bold text-sm">
            📜
          </span>
          <div>
            <h3 className="text-base font-bold tracking-tight">
              Negotiation &amp; Offer History Log
            </h3>
            <p className={`text-xs ${subtextCol}`}>
              Chronological audit log of proposals, counter-offers, and revisions exchanged.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
            quoteState === "UNDER_NEGOTIATION"
              ? "bg-amber-500/15 border-amber-500/30 text-amber-500"
              : quoteState === "SENT"
              ? "bg-blue-500/15 border-blue-500/30 text-blue-500"
              : quoteState === "CONFIRMED"
              ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-500"
              : "bg-slate-500/15 border-slate-500/30 text-slate-400"
          }`}>
            {quoteState === "UNDER_NEGOTIATION"
              ? "⚡ Active Negotiation"
              : quoteState === "SENT"
              ? "📬 Sent / Awaiting Review"
              : quoteState.replace("_", " ")}
          </span>
          <span className={`text-xs font-mono px-2 py-1 rounded ${isInternal ? "bg-slate-100 text-slate-600" : "bg-slate-800 text-slate-300"}`}>
            Quote #Q-{quoteId} · {rounds.length} step{rounds.length === 1 ? "" : "s"}
          </span>
        </div>
      </div>

      {/* Vertical Timeline */}
      <div className="relative pl-6 sm:pl-8 space-y-6 before:absolute before:left-3 sm:before:left-4 before:top-3 before:bottom-3 before:w-0.5 before:bg-slate-200 dark:before:bg-slate-700">
        {rounds.map((round) => {
          const isRep = !round.isCustomer;
          const isAccepted = round.type === "ACCEPTED";
          const isInitial = round.type === "INITIAL_OFFER";

          return (
            <div key={`${round.round}-${round.timestamp}`} className="relative group">
              {/* Bullet node on timeline */}
              <div
                className={`absolute -left-[27px] sm:-left-[35px] top-1.5 flex h-6 w-6 items-center justify-center rounded-full ring-4 text-[10px] font-extrabold ${
                  isAccepted
                    ? "bg-emerald-500 text-white ring-emerald-100 dark:ring-emerald-950/50"
                    : isRep
                    ? "bg-blue-600 text-white ring-blue-100 dark:ring-blue-950/50"
                    : "bg-amber-500 text-white ring-amber-100 dark:ring-amber-950/50"
                }`}
              >
                {round.round}
              </div>

              {/* Card */}
              <div
                className={`rounded-xl border p-4 transition-all ${
                  isAccepted
                    ? isInternal
                      ? "bg-emerald-50/70 border-emerald-300 shadow-2xs"
                      : "bg-emerald-950/30 border-emerald-500/40"
                    : isRep
                    ? isInternal
                      ? "bg-blue-50/40 border-blue-200/90 hover:border-blue-300"
                      : "bg-blue-950/20 border-blue-500/30"
                    : isInternal
                    ? "bg-amber-50/40 border-amber-200/90 hover:border-amber-300"
                    : "bg-amber-950/20 border-amber-500/30"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    {/* Badge Party */}
                    <span
                      className={`text-[11px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-md flex items-center gap-1 ${
                        isAccepted
                          ? "bg-emerald-600 text-white"
                          : isRep
                          ? "bg-blue-600 text-white"
                          : "bg-amber-600 text-white"
                      }`}
                    >
                      {isAccepted
                        ? "🎉 Confirmed Order"
                        : isRep
                        ? (isInitial ? "💼 Initial Proposal" : "💼 Sales Rep Counter-Offer")
                        : "🏢 Customer Counter-Proposal"}
                    </span>

                    <span className="text-xs font-semibold">
                      {round.authorName}
                    </span>
                  </div>

                  <span className={`text-[11px] tabular-nums font-mono ${subtextCol}`}>
                    {round.timestamp ? round.timestamp.slice(0, 19).replace("T", " ") : "Just now"}
                  </span>
                </div>

                {/* Offer Highlights / Commercial Chips */}
                <div className="flex flex-wrap items-center gap-2 my-2.5">
                  {round.discountPct !== null && round.discountPct !== undefined && (
                    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold border ${
                      isRep
                        ? "bg-blue-100/70 border-blue-300 text-blue-900 dark:bg-blue-900/40 dark:border-blue-600 dark:text-blue-200"
                        : "bg-amber-100/70 border-amber-300 text-amber-900 dark:bg-amber-900/40 dark:border-amber-600 dark:text-amber-200"
                    }`}>
                      🏷️ Counter Discount: {round.discountPct.toFixed(1)}%
                    </span>
                  )}

                  {round.deliveryDate && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold border bg-indigo-100/70 border-indigo-300 text-indigo-900 dark:bg-indigo-900/40 dark:border-indigo-600 dark:text-indigo-200">
                      📅 Requested Delivery: {round.deliveryDate}
                    </span>
                  )}

                  {round.productName && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium border bg-slate-100 border-slate-300 text-slate-800 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-200">
                      🎯 Line: {round.productName}
                    </span>
                  )}

                  {round.netTotal !== undefined && round.netTotal !== null && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold border bg-emerald-100/70 border-emerald-300 text-emerald-900 dark:bg-emerald-900/40 dark:border-emerald-600 dark:text-emerald-200">
                      💵 Total Net: {formatCurrency(round.netTotal)}
                    </span>
                  )}
                </div>

                {/* Note / Message Text */}
                {round.body && (
                  <p className={`text-xs leading-relaxed mt-1 ${isInternal ? "text-slate-700" : "text-slate-300"}`}>
                    "{round.body}"
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Bottom Summary Bar & Rep Quick Actions */}
      {isInternal && (
        <div className={`mt-4 pt-4 border-t ${headerBg} flex flex-wrap items-center justify-between gap-3`}>
          <div className="text-xs">
            <span className="font-semibold text-slate-700">Negotiation Status: </span>
            {quoteState === "UNDER_NEGOTIATION" ? (
              <span className="text-amber-600 font-bold">
                Customer counter submitted. Your turn to accept, edit line terms, or make a counter-offer.
              </span>
            ) : quoteState === "SENT" ? (
              <span className="text-blue-600 font-medium">
                Offer delivered to customer portal. You can revise terms anytime if negotiations update.
              </span>
            ) : (
              <span className="text-slate-500">
                Offer is currently in {quoteState.replaceAll("_", " ")} state.
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {latestCustomerCounterPct !== null && latestCustomerCounterPct !== undefined && onAcceptCounter && quoteState === "UNDER_NEGOTIATION" && (
              <button
                type="button"
                onClick={onAcceptCounter}
                className="bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold px-3.5 py-1.5 rounded-lg transition shadow-xs cursor-pointer"
              >
                ⚡ Accept Counter ({latestCustomerCounterPct.toFixed(1)}%)
              </button>
            )}

            {onMakeCounterOffer && (
              <button
                type="button"
                onClick={onMakeCounterOffer}
                className="bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold px-3.5 py-1.5 rounded-lg transition shadow-xs cursor-pointer flex items-center gap-1.5"
              >
                <span>💼 Make Counter-Offer</span>
              </button>
            )}

            {onReviseTerms && (
              <button
                type="button"
                onClick={onReviseTerms}
                className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold px-3.5 py-1.5 rounded-lg transition shadow-xs cursor-pointer flex items-center gap-1.5"
              >
                <span>✏️ Revise Line Items</span>
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
