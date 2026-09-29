"""Hindsight memory layer: everything LedgerMind knows about a vendor lives here.

Each workspace (one browser session) gets its own memory bank so the demo can be
replayed from a blank slate. Memories are tagged `vendor:<slug>` so recall and
reflect stay scoped to the vendor being examined.
"""
import asyncio
import os
import threading
import time
from datetime import datetime

from hindsight_client import Hindsight

from data import VENDORS

BANK_PREFIX = os.environ.get("HINDSIGHT_BANK_PREFIX", "ledgermind")

BANK_MISSION = (
    "You are the long-term memory of LedgerMind, the accounts-payable agent for Golconda Fresh Foods "
    "(Hyderabad). Remember each vendor's normal billing pattern (rates, line items, typical totals, payment "
    "terms), every discrepancy that was flagged, and how the AP team resolved it (credit notes, short-payments, "
    "rejections). Treat renamed charges that are economically the same as the same issue."
)

ASK_STYLE = ("Answer for a busy AP clerk: at most 120 words, short bullet points, no tables, "
             "cite invoice numbers and amounts from memory.")

_client = None
_known_banks = set()

# The client's aiohttp session is bound to one event loop, so every Hindsight call
# runs on a single long-lived loop thread, whatever Flask thread asked for it.
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True, name="hindsight-loop").start()


def _run(coro):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=150)


def client():
    global _client
    if _client is None:
        _client = Hindsight(
            base_url=os.environ["HINDSIGHT_API_URL"],
            api_key=os.environ["HINDSIGHT_API_KEY"],
            timeout=120,
        )
    return _client


def bank_id(workspace):
    return f"{BANK_PREFIX}-{workspace}"


def ensure_bank(workspace):
    bid = bank_id(workspace)
    if bid not in _known_banks:
        _run(client().acreate_bank(bid, name=f"LedgerMind AP · {workspace}", mission=BANK_MISSION))
        _known_banks.add(bid)
    return bid


def reset_bank(workspace):
    bid = bank_id(workspace)
    try:
        _run(client().adelete_bank(bid))
    except Exception:
        pass
    _known_banks.discard(bid)


def vendor_tag(slug):
    return f"vendor:{slug}"


def _serialize(result, source):
    scores = result.scores
    final = scores.get("final") if isinstance(scores, dict) else getattr(scores, "final", None)
    return {
        "id": result.id,
        "text": result.text.split(" | ")[0],
        "type": result.type,
        "date": (result.occurred_start or result.mentioned_at or "")[:10],
        "score": round(float(final or 0), 3),
        "source": source,
        "chunk_id": getattr(result, "chunk_id", None),
    }


def recall_vendor(workspace, invoice):
    """Two recalls run in parallel: the vendor's overall profile, and a semantic
    search for past issues resembling this invoice's line items (catches renamed charges)."""
    bid = ensure_bank(workspace)
    vendor = VENDORS[invoice["vendor"]]
    tags = [vendor_tag(invoice["vendor"])]
    lines = "; ".join(l["description"] for l in invoice["lines"])
    queries = {
        "profile": f"{vendor['name']} billing history: usual rates, line items, totals, payment terms, and decisions",
        "similar": f"Past disputes, surcharges, price changes or duplicates from {vendor['short']} similar to: {lines}. "
                   f"Payment terms Net {invoice['terms_days']}.",
    }

    async def run(name):
        t = time.time()
        resp = await client().arecall(bid, queries[name], tags=tags, tags_match="any_strict", budget="mid",
                                      types=["world", "experience", "observation"], max_tokens=3000,
                                      include_chunks=True, max_chunk_tokens=4000)
        chunks = {cid: c.text for cid, c in (resp.chunks or {}).items()}
        return name, resp.results, chunks, round((time.time() - t) * 1000)

    async def run_all():
        return await asyncio.gather(*(run(name) for name in queries))

    outcomes = _run(run_all())

    merged, timings, chunks = {}, {}, {}
    for name, results, found_chunks, ms in outcomes:
        timings[name] = ms
        chunks.update(found_chunks)
        for r in results:
            if r.id not in merged:
                merged[r.id] = _serialize(r, name)
            else:
                merged[r.id]["source"] = "both"
    memories = sorted(merged.values(), key=lambda m: (m["date"], m["score"]))
    # Source records: the verbatim text each fact was extracted from (keeps rates and terms exact).
    record_ids = list(dict.fromkeys(m["chunk_id"] for m in memories if m["chunk_id"] in chunks))
    records = [{"ref": f"R{i}", "id": cid, "text": chunks[cid]} for i, cid in enumerate(record_ids, 1)]
    record_ref = {r["id"]: r["ref"] for r in records}
    for i, m in enumerate(memories, 1):
        m["ref"] = f"M{i}"
        m["record"] = record_ref.get(m["chunk_id"])
    return {"memories": memories, "records": records, "queries": queries, "timings_ms": timings, "bank": bid}


def retain_invoice(workspace, invoice, analysis, decision, note):
    """Write back what happened so the next invoice from this vendor is judged against it."""
    bid = ensure_bank(workspace)
    vendor = VENDORS[invoice["vendor"]]
    date_label = datetime.fromisoformat(invoice["date"]).strftime("%d %b %Y")
    lines = "; ".join(
        f"{l['description']}: {l['qty']:g} {l['unit']} @ ₹{l['rate']:,.2f} = ₹{l['amount']:,.2f}"
        for l in invoice["lines"]
    )
    flags = analysis.get("flags") or []
    flag_text = " ".join(
        f"[{f.get('severity', '').upper()}] {f.get('title')}: {f.get('detail')}" for f in flags
    ) or "No discrepancies were flagged."
    content = (
        f"Invoice {invoice['number']} from {vendor['name']} dated {date_label} against PO {invoice['po']}. "
        f"Subtotal ₹{invoice['subtotal']:,.2f} plus 18% GST, total ₹{invoice['total']:,.2f}. "
        f"Payment terms on the invoice: Net {invoice['terms_days']}. Line items: {lines}. "
        f"LedgerMind review verdict: {analysis.get('verdict', 'n/a').upper()}. {flag_text} "
        f"AP team decision: {decision.upper()}. Resolution note: {note or 'none'}"
    )
    t = time.time()
    _run(client().aretain(
        bid,
        content,
        timestamp=datetime.fromisoformat(invoice["date"]),
        context=f"Accounts-payable review of a vendor invoice from {vendor['short']}",
        document_id=f"invoice-{invoice['key']}",
        tags=[vendor_tag(invoice["vendor"]), f"decision:{decision}"],
        metadata={"invoice": invoice["number"], "vendor": vendor["slug"], "decision": decision},
    ))
    return {"content": content, "ms": round((time.time() - t) * 1000), "bank": bid}


def ask(workspace, vendor_slug, question):
    bid = ensure_bank(workspace)
    tags = [vendor_tag(vendor_slug)] if vendor_slug else None
    resp = _run(client().areflect(bid, question, budget="low", tags=tags, context=ASK_STYLE,
                                  tags_match="any_strict" if tags else "any", include_facts=True))
    based_on = []
    if resp.based_on and getattr(resp.based_on, "memories", None):
        based_on = [m.text.split(" | ")[0] for m in resp.based_on.memories][:6]
    return {"answer": resp.text, "based_on": based_on}


def vendor_memories(workspace, vendor_slug):
    bid = ensure_bank(workspace)
    resp = _run(client().arecall(bid, f"Everything known about {VENDORS[vendor_slug]['name']}",
                                 tags=[vendor_tag(vendor_slug)], tags_match="any_strict", budget="low",
                                 types=["world", "experience", "observation"], max_tokens=4000))
    return sorted((_serialize(r, "profile") for r in resp.results), key=lambda m: m["date"])
