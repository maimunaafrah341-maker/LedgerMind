"""Synthetic but realistic AP data for the LedgerMind demo.

The buyer is Golconda Fresh Foods, a Hyderabad food distributor. Each vendor
submits invoices over three months; two of them carry a recurring discrepancy
that only becomes visible once the agent remembers earlier invoices.
"""

BUYER = {
    "name": "Golconda Fresh Foods Pvt. Ltd.",
    "address": "Plot 42, IDA Uppal, Hyderabad, Telangana 500039",
    "gstin": "36AAKCG7731M1ZQ",
}

GST_RATE = 0.18


def _line(description, qty, unit, rate, amount=None):
    return {
        "description": description,
        "qty": qty,
        "unit": unit,
        "rate": rate,
        "amount": round(amount if amount is not None else qty * rate, 2),
    }


def _invoice(key, vendor, number, date, terms, po, lines, story):
    subtotal = round(sum(l["amount"] for l in lines), 2)
    tax = round(subtotal * GST_RATE, 2)
    return {
        "key": key,
        "vendor": vendor,
        "number": number,
        "date": date,
        "terms_days": terms,
        "po": po,
        "lines": lines,
        "subtotal": subtotal,
        "tax_rate": GST_RATE,
        "tax": tax,
        "total": round(subtotal + tax, 2),
        "story": story,
    }


VENDORS = {
    "deccan-cold-chain": {
        "slug": "deccan-cold-chain",
        "name": "Deccan Cold Chain Logistics Pvt. Ltd.",
        "short": "Deccan Cold Chain",
        "category": "Refrigerated freight & cold storage",
        "gstin": "36AAGCD4127K1Z8",
        "city": "Shamshabad, Hyderabad",
        "headline": True,
    },
    "kaveri-office": {
        "slug": "kaveri-office",
        "name": "Kaveri Office Supplies & Stationers",
        "short": "Kaveri Office Supplies",
        "category": "Stationery & printer consumables",
        "gstin": "36BJXPK5528R1ZC",
        "city": "Ameerpet, Hyderabad",
        "headline": False,
    },
    "sree-lakshmi": {
        "slug": "sree-lakshmi",
        "name": "Sree Lakshmi Packaging Industries",
        "short": "Sree Lakshmi Packaging",
        "category": "Corrugated boxes & food-grade liners",
        "gstin": "36ADUFS9043H1Z2",
        "city": "Jeedimetla, Hyderabad",
        "headline": False,
    },
}

_freight = lambda chn, blr: [
    _line("Reefer trip Hyderabad → Chennai (627 km, −18 °C)", chn, "trip", 24500),
    _line("Reefer trip Hyderabad → Bengaluru (575 km, −18 °C)", blr, "trip", 22800),
]

INVOICES = [
    # ── Headline scenario: Deccan Cold Chain ────────────────────────────────
    _invoice(
        "dcc-1", "deccan-cold-chain", "DCCL/26-27/0714", "2026-07-08", 45, "GFF-PO-2026-118",
        _freight(4, 3) + [_line("Cold storage, frozen pallet-days (Shamshabad DC)", 120, "pallet-day", 85)],
        "Baseline month. Rates match the PO, Net 45, no surcharges. Nothing to flag.",
    ),
    _invoice(
        "dcc-2", "deccan-cold-chain", "DCCL/26-27/0852", "2026-08-07", 45, "GFF-PO-2026-118",
        _freight(5, 3) + [
            _line("Cold storage, frozen pallet-days (Shamshabad DC)", 140, "pallet-day", 85),
            _line("Fuel surcharge @ 7.5% on freight", 1, "lot", 14317.50),
        ],
        "A 7.5% fuel surcharge appears that the July invoice never had.",
    ),
    _invoice(
        "dcc-3", "deccan-cold-chain", "DCCL/26-27/0981", "2026-09-06", 15, "GFF-PO-2026-118",
        _freight(4, 4) + [
            _line("Cold storage, frozen pallet-days (Shamshabad DC)", 130, "pallet-day", 85),
            _line("HSD price escalation adjustment (diesel index)", 1, "lot", 14190),
        ],
        "The same 7.5% charge returns under a new name, and terms quietly drop to Net 15.",
    ),
    # ── Bonus: Kaveri Office Supplies, unit-price creep ─────────────────────
    _invoice(
        "kos-1", "kaveri-office", "KOS/2026/1187", "2026-07-12", 30, "GFF-PO-2026-131",
        [
            _line("JK Copier A4 75 gsm paper", 60, "ream", 245),
            _line("HP 88A toner cartridge (compatible)", 6, "pc", 2150),
            _line("Box files, foolscap", 40, "pc", 68),
        ],
        "Baseline. A4 paper at the agreed ₹245 per ream.",
    ),
    _invoice(
        "kos-2", "kaveri-office", "KOS/2026/1342", "2026-08-11", 30, "GFF-PO-2026-131",
        [
            _line("JK Copier A4 75 gsm paper", 60, "ream", 268),
            _line("HP 88A toner cartridge (compatible)", 4, "pc", 2150),
        ],
        "A4 paper up 9.4% to ₹268 with no revised quote.",
    ),
    _invoice(
        "kos-3", "kaveri-office", "KOS/2026/1519", "2026-09-10", 30, "GFF-PO-2026-131",
        [
            _line("JK Copier A4 75 gsm paper", 80, "ream", 289),
            _line("HP 88A toner cartridge (compatible)", 6, "pc", 2150),
            _line("Box files, foolscap", 30, "pc", 68),
        ],
        "Paper creeps again to ₹289, now 18% over the agreed rate.",
    ),
    # ── Bonus: Sree Lakshmi Packaging, duplicate resubmission ───────────────
    _invoice(
        "slp-1", "sree-lakshmi", "SLPI/2231", "2026-08-02", 30, "GFF-PO-2026-140",
        [
            _line("5-ply corrugated carton 600×400×300 mm", 2500, "pc", 38.5),
            _line("Food-grade LDPE liner 50 micron", 2500, "pc", 6.2),
        ],
        "Normal packaging order.",
    ),
    _invoice(
        "slp-2", "sree-lakshmi", "SLPI/2231-R1", "2026-08-29", 30, "GFF-PO-2026-140",
        [
            _line("5-ply corrugated carton 600×400×300 mm", 2500, "pc", 38.5),
            _line("Food-grade LDPE liner 50 micron", 2500, "pc", 6.2),
        ],
        "Same goods, same amount, new suffix. A resubmitted duplicate.",
    ),
]

INVOICES_BY_KEY = {inv["key"]: inv for inv in INVOICES}

# Suggested AP notes so the live demo flows without typing. Editable in the UI.
SUGGESTED_NOTES = {
    "dcc-1": "Rates verified against PO GFF-PO-2026-118 (all-inclusive freight). Approved for payment on Net 45.",
    "dcc-2": "Disputed the fuel surcharge: PO GFF-PO-2026-118 is an all-inclusive rate contract with no fuel clause. "
             "Deccan's accounts team (Mr. Raghav Rao) agreed and issued credit note CN-DCCL-0098 for ₹16,894.65 "
             "(₹14,317.50 + GST). Balance approved.",
    "dcc-3": "Short-paid the HSD escalation line (same charge as the August fuel surcharge, renamed). "
             "Rejected the Net 15 terms; contract terms are Net 45. Escalated to procurement for a vendor review.",
    "kos-1": "Paper at the agreed ₹245 per ream. Approved.",
    "kos-2": "Paid at the invoiced rate; asked Kaveri for a revised quote to justify ₹268 per ream.",
    "kos-3": "Held. Paper price has now risen twice without a revised quote. Paying ₹245 per ream per the agreement.",
    "slp-1": "Goods received in full (GRN 8812). Approved.",
    "slp-2": "Rejected as a duplicate of SLPI/2231, which was already paid.",
}


def vendor_invoices(slug):
    return [inv for inv in INVOICES if inv["vendor"] == slug]
