from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable
)
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from datetime import datetime
import uuid
import os

# ── Colour Palette ────────────────────────────────────────────────────────────
ACCENT = colors.HexColor("#4338ca")
DARK   = colors.HexColor("#1e1b4b")
GRAY   = colors.HexColor("#6b7280")
SOFT   = colors.HexColor("#eef2ff")
WHITE  = colors.white

# ── Paragraph Styles (defined once at module level) ───────────────────────────
STYLE_LOGO          = ParagraphStyle("logo", fontSize=24, fontName="Helvetica-Bold", textColor=ACCENT, leading=28)
STYLE_INVOICE_TITLE = ParagraphStyle("invoice", fontSize=24, fontName="Helvetica-Bold", textColor=DARK, alignment=TA_RIGHT, leading=28)
STYLE_TAGLINE       = ParagraphStyle("tagline", fontSize=9, fontName="Helvetica", textColor=GRAY)
STYLE_INVOICE_ID    = ParagraphStyle("invoiceid", fontSize=9, textColor=GRAY, alignment=TA_RIGHT)
STYLE_BILL          = ParagraphStyle("bill", fontSize=11, textColor=DARK)
STYLE_DETAILS       = ParagraphStyle("details", fontSize=11, textColor=DARK, alignment=TA_RIGHT)
STYLE_CLIENT        = ParagraphStyle("client", fontSize=14, fontName="Helvetica-Bold", textColor=DARK, leading=18)
STYLE_META          = ParagraphStyle("meta", fontSize=9, textColor=GRAY, alignment=TA_RIGHT, leading=16)
STYLE_EMAIL         = ParagraphStyle("email", fontSize=10, textColor=GRAY)
STYLE_ADDRESS       = ParagraphStyle("address", fontSize=10, textColor=GRAY)
STYLE_NOTE_HEAD     = ParagraphStyle("notehead", fontSize=11, fontName="Helvetica-Bold", textColor=DARK)
STYLE_NOTE_BODY     = ParagraphStyle("notebody", fontSize=9, textColor=GRAY, leading=16)
STYLE_FOOTER        = ParagraphStyle("footer", fontSize=8, textColor=GRAY, alignment=TA_CENTER)


# ── Helper ────────────────────────────────────────────────────────────────────
def money(x):
    return f"Rs. {x:,.2f}"


# ── Modular Build Functions ───────────────────────────────────────────────────

def _build_header(invoice_id):
    """Returns the logo + INVOICE title block."""
    header_data = [
        [Paragraph("LedgerMind", STYLE_LOGO),               Paragraph("INVOICE", STYLE_INVOICE_TITLE)],
        [Paragraph("Accounts Payable Agent", STYLE_TAGLINE), Paragraph(invoice_id, STYLE_INVOICE_ID)]
    ]
    table = Table(header_data, colWidths=[9*cm, 7*cm])
    table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _build_client_info(data, date):
    """Returns the Bill To / Invoice Details block."""
    info_data = [
        [
            Paragraph("<b>Bill To</b>",         STYLE_BILL),
            Paragraph("<b>Invoice Details</b>",  STYLE_DETAILS)
        ],
        [
            Paragraph(data["client_name"], STYLE_CLIENT),
            Paragraph(f"<b>Date:</b> {date}<br/><b>Status:</b> Generated", STYLE_META)
        ],
        [Paragraph(data.get("client_email",   ""), STYLE_EMAIL),   ""],
        [Paragraph(data.get("client_address", ""), STYLE_ADDRESS), ""]
    ]
    table = Table(info_data, colWidths=[10*cm, 6*cm])
    table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _build_items_table(items, tax_rate):
    """Builds the line-items table and returns (table, total)."""
    rows = [["#", "Description", "Qty", "Price", "Amount"]]
    subtotal = 0

    for i, item in enumerate(items, start=1):
        line_total = item["qty"] * item["price"]
        subtotal  += line_total
        rows.append([
            str(i), item["name"], str(item["qty"]),
            money(item["price"]), money(line_total)
        ])

    tax_amount = subtotal * tax_rate
    total      = subtotal + tax_amount

    rows.append(["", "", "", "Subtotal", money(subtotal)])
    if tax_rate > 0:
        rows.append(["", "", "", f"Tax ({int(tax_rate * 100)}%)", money(tax_amount)])
    rows.append(["", "", "", "TOTAL", money(total)])

    total_row = len(rows) - 1

    table = Table(rows,
                  colWidths=[1*cm, 7.5*cm, 2*cm, 2.8*cm, 3*cm],
                  repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0),  (-1, 0),                ACCENT),
        ("TEXTCOLOR",     (0, 0),  (-1, 0),                WHITE),
        ("FONTNAME",      (0, 0),  (-1, 0),                "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0),  (-1, 0),                10),
        ("TOPPADDING",    (0, 0),  (-1, 0),                10),
        ("BOTTOMPADDING", (0, 0),  (-1, 0),                10),
        ("FONTNAME",      (0, 1),  (-1, -1),               "Helvetica"),
        ("FONTSIZE",      (0, 1),  (-1, -1),               9),
        ("ROWBACKGROUNDS",(0, 1),  (-1, -4),               [WHITE, SOFT]),
        ("TOPPADDING",    (0, 1),  (-1, -1),               8),
        ("BOTTOMPADDING", (0, 1),  (-1, -1),               8),
        ("LINEBELOW",     (0, 1),  (-1, -4),               0.3, colors.HexColor("#e5e7eb")),
        ("ALIGN",         (0, 0),  (0, -1),                "CENTER"),
        ("ALIGN",         (2, 0),  (-1, -1),               "RIGHT"),
        ("FONTNAME",      (3, -3), (-1, -1),               "Helvetica-Bold"),
        ("BACKGROUND",    (3, total_row), (-1, total_row), ACCENT),
        ("TEXTCOLOR",     (3, total_row), (-1, total_row), WHITE),
        ("TOPPADDING",    (3, total_row), (-1, total_row), 10),
        ("BOTTOMPADDING", (3, total_row), (-1, total_row), 10),
        ("FONTSIZE",      (3, total_row), (-1, total_row), 11),
    ]))

    return table, total


def _build_notes(notes):
    """Returns notes section as a list of flowables."""
    return [
        Spacer(1, 0.8*cm),
        Paragraph("Notes", STYLE_NOTE_HEAD),
        Spacer(1, 0.12*cm),
        Paragraph(notes, STYLE_NOTE_BODY)
    ]


def _build_footer():
    """Returns the footer divider and credit line."""
    return [
        Spacer(1, 1.3*cm),
        HRFlowable(width="100%", thickness=0.5,
                   color=colors.HexColor("#d1d5db"), spaceAfter=8),
        Paragraph("Processed by LedgerMind • Accounts Payable Agent", STYLE_FOOTER)
    ]


# ── Main Entry Point ──────────────────────────────────────────────────────────

def generate_invoice(data, output_dir):
    """
    Orchestrates invoice generation by calling focused helper functions.
    Each section of the PDF is built independently and assembled here.
    """
    invoice_id = f"INV-{datetime.now().strftime('%Y%m')}-{str(uuid.uuid4())[:6].upper()}"
    filename   = f"{invoice_id}.pdf"
    filepath   = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=1.8*cm, bottomMargin=1.8*cm
    )

    date = datetime.now().strftime("%B %d, %Y")
    items_table, total = _build_items_table(data["items"], data.get("tax_rate", 0))

    story = [
        _build_header(invoice_id),
        HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceBefore=10, spaceAfter=18),
        _build_client_info(data, date),
        Spacer(1, 0.7*cm),
        items_table,
    ]

    if data.get("notes"):
        story.extend(_build_notes(data["notes"]))

    story.extend(_build_footer())

    doc.build(story)
    return invoice_id, filename, total
