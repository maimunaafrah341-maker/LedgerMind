"""LedgerMind: an accounts-payable agent that remembers every vendor."""
import os
import secrets
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from flask import Flask, Response, jsonify, render_template, request, session  # noqa: E402

import agent  # noqa: E402
import database as db  # noqa: E402
import memory  # noqa: E402
from data import BUYER, INVOICES, INVOICES_BY_KEY, SUGGESTED_NOTES, VENDORS  # noqa: E402
from generator import dispute_notice  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ledgermind-dev-secret")
db.init_db()

DECISIONS = {"approve", "hold", "reject"}


def workspace():
    if "ws" not in session:
        session["ws"] = secrets.token_hex(4)
        session.permanent = True
    return session["ws"]


def _error(msg, code=400):
    return jsonify({"error": msg}), code


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def state():
    ws = workspace()
    return jsonify({
        "workspace": ws,
        "bank": memory.bank_id(ws),
        "buyer": BUYER,
        "vendors": list(VENDORS.values()),
        "invoices": INVOICES,
        "notes": SUGGESTED_NOTES,
        "postings": db.postings(ws),
        "reviews": db.reviews(ws),
        "model": agent.MODEL,
    })


@app.post("/api/analyze/<key>")
def analyze(key):
    invoice = INVOICES_BY_KEY.get(key)
    if not invoice:
        return _error("Unknown invoice", 404)
    ws = workspace()
    t = time.time()
    try:
        recalled = memory.recall_vendor(ws, invoice)
    except Exception as e:
        return _error(f"Hindsight recall failed: {e}", 502)
    prior = {p["number"] for p in db.postings(ws) if p["invoice_key"] != key}
    result = agent.review(invoice, recalled["memories"], recalled["records"], prior)
    payload = {**recalled, **result, "invoice_key": key, "total_ms": round((time.time() - t) * 1000)}
    db.save_review(ws, key, payload)
    return jsonify(payload)


@app.post("/api/commit/<key>")
def commit(key):
    invoice = INVOICES_BY_KEY.get(key)
    body = request.get_json(silent=True) or {}
    decision, note = body.get("decision"), (body.get("note") or "").strip()[:1500]
    if not invoice:
        return _error("Unknown invoice", 404)
    if decision not in DECISIONS:
        return _error("Decision must be approve, hold or reject")
    ws = workspace()
    review = db.get_review(ws, key)
    if not review:
        return _error("Examine the invoice before posting it")
    analysis = review["with_memory"]
    try:
        retained = memory.retain_invoice(ws, invoice, analysis, decision, note)
    except Exception as e:
        return _error(f"Hindsight retain failed: {e}", 502)
    db.save_posting(ws, invoice, analysis["verdict"], decision, note, analysis.get("amount_at_risk") or 0,
                    retained["content"])
    return jsonify({"retained": retained, "postings": db.postings(ws)})


@app.post("/api/ask")
def ask():
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()[:500]
    vendor = body.get("vendor")
    if not question:
        return _error("Ask a question")
    if vendor and vendor not in VENDORS:
        return _error("Unknown vendor", 404)
    try:
        return jsonify(memory.ask(workspace(), vendor, question))
    except Exception as e:
        return _error(f"Hindsight reflect failed: {e}", 502)


@app.get("/api/vendor/<slug>/memory")
def vendor_memory(slug):
    if slug not in VENDORS:
        return _error("Unknown vendor", 404)
    try:
        return jsonify({"memories": memory.vendor_memories(workspace(), slug)})
    except Exception as e:
        return _error(f"Hindsight recall failed: {e}", 502)


@app.get("/api/dispute/<key>.pdf")
def dispute(key):
    invoice = INVOICES_BY_KEY.get(key)
    ws = workspace()
    review = db.get_review(ws, key) if invoice else None
    if not review:
        return _error("No review for this invoice yet", 404)
    note = next((p["note"] for p in db.postings(ws) if p["invoice_key"] == key), "")
    pdf = dispute_notice(invoice, review, note)
    filename = f"dispute-{invoice['number'].replace('/', '-')}.pdf"
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


@app.post("/api/reset")
def reset():
    ws = workspace()
    memory.reset_bank(ws)
    db.clear_workspace(ws)
    session["ws"] = secrets.token_hex(4)
    return jsonify({"workspace": session["ws"]})


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
