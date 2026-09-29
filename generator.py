"""Generates the vendor dispute / short-payment notice PDF for a held invoice."""
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from data import BUYER, VENDORS

# ── Ledger palette (matches the web UI) ───────────────────────────────────────
INK = colors.HexColor("#1B2420")
GREEN = colors.HexColor("#2F5D50")
RED = colors.HexColor("#B3261E")
RULE = colors.HexColor("#9DB4CF")
PAPER = colors.HexColor("#F6F2E7")
MUTED = colors.HexColor("#5E6660")

S_BRAND = ParagraphStyle("brand", fontName="Times-Bold", fontSize=22, textColor=GREEN, leading=26)
S_TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=13, textColor=RED, alignment=TA_RIGHT)
S_META = ParagraphStyle("meta", fontName="Helvetica", fontSize=9, textColor=MUTED, leading=13)
S_META_R = ParagraphStyle("metar", parent=S_META, alignment=TA_RIGHT)
S_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10, textColor=INK, leading=15)
S_HEAD = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=10.5, textColor=INK, spaceBefore=6)
S_CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, textColor=INK, leading=11)


def _pdf_text(s):
    # Base-14 fonts lack these glyphs.
    return (s or "").replace("₹", "Rs. ").replace("→", "to").replace("−", "-")


def money(x):
    return f"Rs. {x:,.2f}"


def dispute_notice(invoice, review, note):
    vendor = VENDORS[invoice["vendor"]]
    analysis = review["with_memory"]
    flags = analysis.get("flags") or []
    flagged_lines = {f.get("line_index") for f in flags if f.get("line_index") is not None}
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title=f"Dispute notice {invoice['number']}")

    header = Table([[Paragraph("LedgerMind", S_BRAND), Paragraph("INVOICE DISPUTE NOTICE", S_TITLE)],
                    [Paragraph(f"{BUYER['name']}<br/>{BUYER['address']}<br/>GSTIN {BUYER['gstin']}", S_META),
                     Paragraph(f"Date: {datetime.now():%d %b %Y}<br/>Ref: {invoice['number']}<br/>PO: {invoice['po']}",
                               S_META_R)]],
                   colWidths=[9.5 * cm, 7.5 * cm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))

    rows = [["#", "Description", "Qty", "Rate", "Amount", "Status"]]
    for i, l in enumerate(invoice["lines"]):
        rows.append([str(i + 1), Paragraph(_pdf_text(l["description"]), S_CELL), f"{l['qty']:g}",
                     money(l["rate"]), money(l["amount"]), "DISPUTED" if i in flagged_lines else "OK"])
    rows += [["", "", "", "Subtotal", money(invoice["subtotal"]), ""],
             ["", "", "", "GST 18%", money(invoice["tax"]), ""],
             ["", "", "", "Invoiced", money(invoice["total"]), ""]]
    t = Table(rows, colWidths=[0.8 * cm, 7.2 * cm, 1.3 * cm, 2.6 * cm, 2.9 * cm, 2.2 * cm], repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), GREEN), ("LINEBELOW", (0, 0), (-1, 0), 1, GREEN),
        ("LINEBELOW", (0, 1), (-1, -4), 0.4, RULE), ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("FONTNAME", (3, -3), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (3, -1), (4, -1), 1, INK),
    ]
    for i in flagged_lines:
        style += [("TEXTCOLOR", (0, i + 1), (-1, i + 1), RED), ("BACKGROUND", (0, i + 1), (-1, i + 1), PAPER)]
    t.setStyle(TableStyle(style))

    story = [header, HRFlowable(width="100%", thickness=1.2, color=GREEN, spaceBefore=8, spaceAfter=14),
             Paragraph(f"To: Accounts Receivable, <b>{vendor['name']}</b>, {vendor['city']} (GSTIN {vendor['gstin']})",
                       S_BODY),
             Spacer(1, 8),
             Paragraph(f"We have reviewed invoice <b>{invoice['number']}</b> dated {invoice['date']} and are unable to "
                       f"release it in full for the reasons below.", S_BODY),
             Spacer(1, 10), t, Spacer(1, 12), Paragraph("Discrepancies", S_HEAD)]
    for n, f in enumerate(flags, 1):
        tag = " (recurring)" if f.get("recurring") else ""
        story.append(Paragraph(f"{n}. <b>{_pdf_text(f.get('title'))}</b>{tag}: {_pdf_text(f.get('detail'))}", S_BODY))
    at_risk = analysis.get("amount_at_risk") or 0
    if at_risk:
        story += [Spacer(1, 8), Paragraph(
            f"Amount withheld: <b>{money(at_risk)}</b> plus applicable GST. Please issue a credit note or a revised "
            f"invoice. Payment terms remain as agreed in the purchase order.", S_BODY)]
    if note:
        story += [Paragraph("AP note", S_HEAD), Paragraph(_pdf_text(note), S_BODY)]
    story += [Spacer(1, 24), HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=6),
              Paragraph("Prepared by LedgerMind, the accounts-payable agent with vendor memory by Hindsight.", S_META)]
    doc.build(story)
    return buf.getvalue()
