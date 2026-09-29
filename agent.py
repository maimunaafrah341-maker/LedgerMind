"""The AP reviewer: deterministic checks + an LLM judgement grounded in recalled memory.

Every invoice is reviewed twice in parallel, once with Hindsight memory and once
stateless, so the UI can show exactly what memory changed.
"""
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from groq import Groq

from data import BUYER, VENDORS

MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
_groq = None
DISPUTE_WORDS = re.compile(r"disput|credit note|short-?paid|on hold|placed .* hold|held|reject|duplicate|overbill|revised quote|queried", re.I)


def groq():
    global _groq
    if _groq is None:
        _groq = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq


def rule_checks(invoice, prior_numbers):
    """Checks that need no memory: arithmetic and exact duplicate numbers."""
    issues = []
    for i, l in enumerate(invoice["lines"]):
        if l["unit"] != "lot" and abs(l["qty"] * l["rate"] - l["amount"]) > 0.5:
            issues.append({"line_index": i, "title": "Line total does not match qty × rate",
                           "detail": f"{l['qty']} × {l['rate']} ≠ {l['amount']}"})
    if abs(round(invoice["subtotal"] * invoice["tax_rate"], 2) - invoice["tax"]) > 0.5:
        issues.append({"line_index": None, "title": "GST miscalculated", "detail": "Tax ≠ 18% of subtotal"})
    if invoice["number"] in prior_numbers:
        issues.append({"line_index": None, "title": "Invoice number already posted",
                       "detail": f"{invoice['number']} exists in the ledger"})
    return issues


SYSTEM = f"""You are LedgerMind, the accounts-payable review agent for {BUYER['name']}.
You review one incoming vendor invoice. You may be given MEMORIES [M#]: facts your memory system (Hindsight) recalled
about this vendor from earlier invoices, flags and AP resolutions, plus SOURCE RECORDS [R#]: the verbatim notes those
facts came from (exact line items, rates, terms). Use them as your only knowledge of history; cite M refs.

Flag an issue only when the invoice itself or a memory supports it. Look for:
- charges or line types that did not appear on earlier invoices, or were previously disputed/credited
  (treat a renamed charge that is economically the same, e.g. same % of freight, as the SAME recurring issue)
- payment terms different from what was previously agreed
- unit rates that changed versus remembered rates
- duplicates of an invoice already processed (same goods and amount, new number)
- totals far outside the vendor's normal range
Compare the invoice line by line and the payment terms against the most recent remembered invoice.
If there are no memories, you have no history: judge only internal consistency and do not invent a baseline.
A clean invoice with no issues should be approved with an empty flags list.

Severity rules:
- An issue that matches something previously disputed, credited, short-paid or rejected is recurring=true,
  severity "high", and the verdict must be "hold".
- A new charge type or a payment-terms change versus history is at least "medium" and the verdict is at least "review".
- A total that is higher only because volumes (trips, quantities) rose at the same rates is NOT an issue.
- amount_at_risk is only the specific overbilled amount (a disputed line, or qty × rate increase), excluding GST;
  it is 0 for terms changes and general volume changes. Give one flag per distinct issue.

Return ONLY JSON:
{{
 "verdict": "approve" | "review" | "hold",
 "confidence": 0.0-1.0,
 "headline": "one short sentence, plain English",
 "reasoning": "2-3 sentences explaining the verdict, referencing memories like [M2]",
 "flags": [{{
   "line_index": integer index into LINES or null,
   "kind": "new_charge" | "recurring_issue" | "terms_change" | "price_change" | "duplicate" | "amount_spike" | "arithmetic",
   "severity": "low" | "medium" | "high",
   "title": "short title",
   "detail": "one or two sentences with specific numbers",
   "memory_refs": ["M1"],
   "recurring": true | false,
   "amount_at_risk": number (rupees, excluding GST, 0 if not monetary)
 }}],
 "recommended_action": "one sentence telling the AP clerk what to do"
}}"""


def _invoice_block(invoice):
    v = VENDORS[invoice["vendor"]]

    def share(i, l):
        # Lump-sum lines are expressed as a % of the rest, so renamed percentage surcharges stay comparable.
        rest = sum(x["amount"] for j, x in enumerate(invoice["lines"]) if j != i)
        return f" | = {l['amount'] / rest * 100:.2f}% of the other lines" if l["unit"] == "lot" and rest else ""

    lines = "\n".join(
        f"  [{i}] {l['description']} | qty {l['qty']:g} {l['unit']} | rate ₹{l['rate']:,.2f} | amount ₹{l['amount']:,.2f}"
        f"{share(i, l)}"
        for i, l in enumerate(invoice["lines"])
    )
    return (f"VENDOR: {v['name']} ({v['category']})\nINVOICE: {invoice['number']} dated {invoice['date']}, "
            f"PO {invoice['po']}, payment terms Net {invoice['terms_days']}\nLINES:\n{lines}\n"
            f"SUBTOTAL ₹{invoice['subtotal']:,.2f} | GST 18% ₹{invoice['tax']:,.2f} | TOTAL ₹{invoice['total']:,.2f}")


def _ask_llm(invoice, memories, records, rule_issues, effort="medium"):
    if memories:
        mem = "\n".join(f"[{m['ref']}] ({m['date']}, {m['type']}) {m['text']}" for m in memories)
        mem += "\n\nSOURCE RECORDS:\n" + "\n".join(f"[{r['ref']}] {r['text']}" for r in records)
    else:
        mem = "(none: no history for this vendor is available)"
    checks = "\n".join(f"- {i['title']}: {i['detail']}" for i in rule_issues) or "- all arithmetic checks passed"
    user = f"{_invoice_block(invoice)}\n\nSYSTEM CHECKS:\n{checks}\n\nMEMORIES:\n{mem}"
    t = time.time()
    resp = groq().chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        temperature=0.1,
        reasoning_effort=effort,
        max_completion_tokens=4000,
    )
    out = json.loads(resp.choices[0].message.content)
    out["ms"] = round((time.time() - t) * 1000)
    return _normalize(out, memories)


def _normalize(out, memories):
    valid_refs = {m["ref"] for m in memories}
    out["verdict"] = out.get("verdict") if out.get("verdict") in ("approve", "review", "hold") else "review"
    flags = []
    for f in out.get("flags") or []:
        f["memory_refs"] = [r for r in (f.get("memory_refs") or []) if r in valid_refs]
        f["severity"] = f.get("severity") if f.get("severity") in ("low", "medium", "high") else "medium"
        try:
            f["amount_at_risk"] = float(f.get("amount_at_risk") or 0)
        except (TypeError, ValueError):
            f["amount_at_risk"] = 0.0
        flags.append(f)
    # Guard: a flag grounded in a memory of a past dispute is a recurring issue, and recurring issues are held.
    disputed = {m["ref"] for m in memories if DISPUTE_WORDS.search(m["text"])}
    for f in flags:
        if f.get("kind") in ("new_charge", "price_change", "recurring_issue", "duplicate") and disputed & set(f["memory_refs"]):
            f["recurring"], f["severity"], f["kind"] = True, "high", "recurring_issue"
        if f.get("kind") == "duplicate":
            f["severity"] = "high"
    if any((f.get("recurring") or f.get("kind") == "duplicate") and f["severity"] == "high" for f in flags):
        out["verdict"] = "hold"
    out["flags"] = flags
    out["amount_at_risk"] = round(sum(f["amount_at_risk"] for f in flags), 2)
    return out


def _fallback(rule_issues, error):
    return {
        "verdict": "review",
        "confidence": 0.3,
        "headline": "The reasoning model was unavailable, so only rule checks ran.",
        "reasoning": f"LLM error: {error}",
        "flags": [dict(i, kind="arithmetic", severity="medium", memory_refs=[], recurring=False, amount_at_risk=0)
                  for i in rule_issues],
        "recommended_action": "Review manually.",
        "amount_at_risk": 0,
        "ms": 0,
    }


def review(invoice, memories, records, prior_numbers):
    rule_issues = rule_checks(invoice, prior_numbers)

    def safe(mem):
        try:
            # The stateless baseline needs less thinking; keeps us under Groq's free-tier token limits.
            return _ask_llm(invoice, mem, records if mem else [], rule_issues, "medium" if mem else "low")
        except Exception as e:  # keep the demo alive if the LLM hiccups
            return _fallback(rule_issues, e)

    with ThreadPoolExecutor(2) as pool:
        with_mem = pool.submit(safe, memories)
        stateless = pool.submit(safe, [])
        return {"with_memory": with_mem.result(), "stateless": stateless.result(), "rule_checks": rule_issues}
