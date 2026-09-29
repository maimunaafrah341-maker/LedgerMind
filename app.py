from flask import Flask, render_template, request, send_file, redirect, url_for
from generator import generate_invoice
from database import init_db, save_invoice, get_all_invoices
import os

app = Flask(__name__)
INVOICES_DIR = "invoices"
os.makedirs(INVOICES_DIR, exist_ok=True)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():

    # ── Validate Client Name ──────────────────────────────────
    client_name = request.form.get("client_name", "").strip()
    client_email = request.form.get("client_email", "").strip()
    client_addr = request.form.get("client_address", "").strip()

    if not client_name:
        return render_template("index.html", error="Client name is required.")

    # ── Parse & Validate Line Items ───────────────────────────
    item_names  = request.form.getlist("item_name[]")
    item_qtys   = request.form.getlist("item_qty[]")
    item_prices = request.form.getlist("item_price[]")

    items = []
    for name, qty, price in zip(item_names, item_qtys, item_prices):
        name  = name.strip()
        qty   = qty.strip()
        price = price.strip()

        if not (name and qty and price):
            continue  # skip blank rows silently

        try:
            qty_val   = int(qty)
            price_val = float(price)
        except ValueError:
            return render_template(
                "index.html",
                error=f"Quantity and price must be valid numbers. Check item '{name}'."
            )

        if qty_val <= 0:
            return render_template(
                "index.html",
                error=f"Quantity must be greater than zero. Check item '{name}'."
            )
        if price_val < 0:
            return render_template(
                "index.html",
                error=f"Price cannot be negative. Check item '{name}'."
            )

        items.append({"name": name, "qty": qty_val, "price": price_val})

    if not items:
        return render_template("index.html", error="Please add at least one item.")

    # ── Parse Tax Rate ────────────────────────────────────────
    try:
        tax_raw  = request.form.get("tax_rate", "0") or "0"
        tax_rate = float(tax_raw) / 100
    except ValueError:
        tax_rate = 0.0

    notes = request.form.get("notes", "").strip()

    invoice_data = {
        "client_name":    client_name,
        "client_email":   client_email,
        "client_address": client_addr,
        "items":          items,
        "tax_rate":       tax_rate,
        "notes":          notes
    }

    # ── Generate PDF ──────────────────────────────────────────
    try:
        invoice_id, filename, total = generate_invoice(invoice_data, INVOICES_DIR)
    except Exception as e:
        return render_template("index.html", error=f"PDF generation failed: {str(e)}")

    # ── Save to Database ──────────────────────────────────────
    try:
        save_invoice(invoice_id, client_name, total, filename)
    except Exception as e:
        return render_template("index.html", error=f"Could not save invoice record: {str(e)}")

    return redirect(url_for("success",
                            invoice_id=invoice_id,
                            filename=filename,
                            total=f"{total:.2f}"))


@app.route("/success")
def success():
    return render_template("success.html",
                           invoice_id=request.args.get("invoice_id"),
                           filename=request.args.get("filename"),
                           total=request.args.get("total"))


@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(INVOICES_DIR, filename)
    if not os.path.exists(path):
        return render_template("index.html", error="Invoice file not found.")
    return send_file(path, as_attachment=True)


@app.route("/history")
def history():
    invoices = get_all_invoices()
    return render_template("history.html", invoices=invoices)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
