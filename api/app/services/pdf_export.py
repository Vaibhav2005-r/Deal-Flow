"""PDF Quotation document generator (§11, Phase 6).

Produces an official, clean B2B quotation document containing customer details,
commercial line items, discount breakdown, total amount due, and validity notice.
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from sqlalchemy.orm import Session

from app.models.tables import Customer, Product, Quotation, QuoteLine, User


def generate_quote_pdf(session: Session, quote: Quotation) -> bytes:
    """Renders an official Quotation PDF document."""
    customer = session.get(Customer, quote.customer_id)
    rep = session.get(User, quote.rep_id) if quote.rep_id else None
    lines = quote.lines

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # Standard Letter / A4 portrait canvas (8.5 x 11 in)
        fig = plt.figure(figsize=(8.5, 11), dpi=150)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")

        # Background header bar
        ax.fill_between([0.05, 0.95], [0.93, 0.93], [0.85, 0.85], color="#1e293b")

        # Company branding
        ax.text(0.08, 0.89, "DEALFLOW 360", fontsize=18, fontweight="bold", color="#ffffff", va="center")
        ax.text(0.08, 0.865, "B2B Sales Operations Platform · Official Commercial Quotation", fontsize=8.5, color="#94a3b8", va="center")

        # Quotation meta top right
        ax.text(0.92, 0.90, f"QUOTE #{quote.id}", fontsize=14, fontweight="bold", color="#ffffff", ha="right", va="center")
        ax.text(0.92, 0.875, f"Revision: v{quote.version}  ·  Status: {quote.state}", fontsize=9, color="#cbd5e1", ha="right", va="center")
        act_date = quote.last_activity_at.strftime("%Y-%m-%d") if quote.last_activity_at else quote.created_at.strftime("%Y-%m-%d")
        ax.text(0.92, 0.855, f"Date: {act_date}", fontsize=8, color="#94a3b8", ha="right", va="center")

        # Customer & Rep info blocks
        ax.text(0.08, 0.81, "CUSTOMER DETAILS", fontsize=9, fontweight="bold", color="#475569")
        ax.text(0.08, 0.785, customer.name if customer else "N/A", fontsize=11, fontweight="bold", color="#0f172a")
        tier_str = f"Tier: {customer.tier.upper()}" if customer else ""
        ax.text(0.08, 0.765, f"Account Tier: {tier_str}", fontsize=9, color="#64748b")

        ax.text(0.55, 0.81, "SALES REPRESENTATIVE", fontsize=9, fontweight="bold", color="#475569")
        ax.text(0.55, 0.785, rep.full_name if rep else "Direct Sales", fontsize=11, fontweight="bold", color="#0f172a")
        ax.text(0.55, 0.765, rep.email if rep else "sales@dealflow.example", fontsize=9, color="#64748b")

        # Dividing rule
        ax.plot([0.08, 0.92], [0.74, 0.74], color="#e2e8f0", lw=1.2)

        # Line items table header
        y = 0.71
        ax.fill_between([0.08, 0.92], [y + 0.02, y + 0.02], [y - 0.01, y - 0.01], color="#f8fafc")
        ax.text(0.09, y, "#", fontsize=8.5, fontweight="bold", color="#475569")
        ax.text(0.13, y, "Product / SKU", fontsize=8.5, fontweight="bold", color="#475569")
        ax.text(0.48, y, "Category", fontsize=8.5, fontweight="bold", color="#475569")
        ax.text(0.60, y, "Qty", fontsize=8.5, fontweight="bold", color="#475569", ha="right")
        ax.text(0.72, y, "Unit Price", fontsize=8.5, fontweight="bold", color="#475569", ha="right")
        ax.text(0.80, y, "Disc %", fontsize=8.5, fontweight="bold", color="#475569", ha="right")
        ax.text(0.91, y, "Net Value", fontsize=8.5, fontweight="bold", color="#475569", ha="right")

        # Table rows
        y -= 0.035
        total_list = Decimal(0)
        total_net = Decimal(0)

        for idx, ln in enumerate(lines, 1):
            prod = session.get(Product, ln.product_id)
            list_val = ln.unit_price * Decimal(ln.qty)
            net_val = list_val * (Decimal(1) - ln.discount_pct / Decimal(100))
            total_list += list_val
            total_net += net_val

            ax.text(0.09, y, str(idx), fontsize=8, color="#64748b")
            pname = prod.name[:32] if prod else f"Item {ln.product_id}"
            ax.text(0.13, y, pname, fontsize=8.5, fontweight="medium", color="#1e293b")
            ax.text(0.48, y, prod.category if prod else "-", fontsize=8, color="#64748b")
            ax.text(0.60, y, str(ln.qty), fontsize=8.5, color="#1e293b", ha="right")
            ax.text(0.72, y, f"${ln.unit_price:,.2f}", fontsize=8.5, color="#475569", ha="right")
            ax.text(0.80, y, f"{ln.discount_pct:.1f}%", fontsize=8.5, color="#2563eb", ha="right")
            ax.text(0.91, y, f"${net_val:,.2f}", fontsize=8.5, fontweight="semibold", color="#0f172a", ha="right")

            ax.plot([0.08, 0.92], [y - 0.012, y - 0.012], color="#f1f5f9", lw=0.8)
            y -= 0.03
            if y < 0.35:
                break

        # Summary box
        y -= 0.02
        tot_discount = total_list - total_net
        eff_discount = float(round(Decimal(100) * tot_discount / total_list, 1)) if total_list > 0 else 0.0

        ax.fill_between([0.55, 0.92], [y + 0.01, y + 0.01], [y - 0.12, y - 0.12], color="#f8fafc")
        ax.plot([0.55, 0.92, 0.92, 0.55, 0.55], [y + 0.01, y + 0.01, y - 0.12, y - 0.12, y + 0.01], color="#e2e8f0", lw=1)

        sy = y - 0.015
        ax.text(0.58, sy, "Subtotal (List Value):", fontsize=8.5, color="#64748b")
        ax.text(0.89, sy, f"${total_list:,.2f}", fontsize=8.5, color="#334155", ha="right")

        sy -= 0.025
        ax.text(0.58, sy, f"Discount Savings ({eff_discount}%):", fontsize=8.5, color="#2563eb")
        ax.text(0.89, sy, f"-${tot_discount:,.2f}", fontsize=8.5, color="#2563eb", ha="right")

        sy -= 0.03
        ax.plot([0.57, 0.90], [sy + 0.015, sy + 0.015], color="#cbd5e1", lw=1)
        ax.text(0.58, sy, "Net Total Amount:", fontsize=10, fontweight="bold", color="#0f172a")
        ax.text(0.89, sy, f"${total_net:,.2f}", fontsize=11, fontweight="bold", color="#0f172a", ha="right")

        # Narrative / Executive Summary if present
        if quote.narrative:
            ny = y - 0.16
            ax.text(0.08, ny, "EXECUTIVE SUMMARY & DEAL RATIONALE", fontsize=8.5, fontweight="bold", color="#475569")
            ax.text(0.08, ny - 0.02, quote.narrative[:300], fontsize=8, color="#334155", wrap=True)

        # Footer & Validity terms
        fy = 0.08
        ax.plot([0.08, 0.92], [fy + 0.04, fy + 0.04], color="#e2e8f0", lw=1)
        ax.text(0.08, fy + 0.02, "TERMS & CONDITIONS", fontsize=8, fontweight="bold", color="#64748b")
        ax.text(0.08, fy, "This quotation is valid for 30 calendar days from the issue date. Orders are subject to standard enterprise agreement terms.", fontsize=7.5, color="#94a3b8")
        ax.text(0.08, fy - 0.015, "Generated automatically by DealFlow360 Enterprise Sales Platform.", fontsize=7, color="#cbd5e1")

        pdf.savefig(fig)
        plt.close(fig)

    buf.seek(0)
    return buf.read()
