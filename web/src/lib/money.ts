/**
 * Currency formatting — shared by both trees.
 *
 * This lives in `lib/` rather than `internal/components` because the customer
 * portal may not import from `src/internal` (§1 constraint 2), and the portal
 * had grown its own private copy of the formatter as a result. Two copies is
 * how the same figure ends up rendered two different ways.
 */

// Two decimals always: the internal tables were rendering "₹3,50,172"
// beside "₹8,19,837.5", which reads as ragged rather than as money.
const nf = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** A number, grouped Indian-style. No symbol — use `currency` for that. */
export const money = (v: string | number | null | undefined) => {
  if (v === null || v === undefined) return "0.00";
  return nf.format(Number(v));
};

/**
 * The one place the currency symbol is decided.
 *
 * Every price in the seed and every NUMERIC column is rupees; the UI was
 * printing "$" in twenty-odd places, which made the same figure read as
 * dollars on one screen and rupees on another. Formatting lives here so the
 * symbol and the grouping cannot drift apart again.
 */
export const currency = (v: string | number | null | undefined) => `₹${money(v)}`;
