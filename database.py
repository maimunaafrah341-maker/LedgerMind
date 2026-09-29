import sqlite3
from datetime import datetime

DB_PATH = "invoices.db"


def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id          TEXT PRIMARY KEY,
                client_name TEXT NOT NULL,
                total       REAL NOT NULL,
                filename    TEXT NOT NULL,
                created_at  TEXT NOT NULL
            )
        """)
        conn.commit()
        print("[DB] Initialized invoices.db")
    except sqlite3.Error as e:
        print(f"[DB ERROR] Could not initialize database: {e}")
        raise
    finally:
        conn.close()


def save_invoice(invoice_id, client_name, total, filename):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO invoices VALUES (?,?,?,?,?)",
            (invoice_id, client_name, total, filename, datetime.now().isoformat())
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f"Invoice ID '{invoice_id}' already exists.")
    except sqlite3.Error as e:
        raise RuntimeError(f"Database error while saving invoice: {e}")
    finally:
        conn.close()


def get_all_invoices():
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT * FROM invoices ORDER BY created_at DESC"
        ).fetchall()
        return rows
    except sqlite3.Error as e:
        print(f"[DB ERROR] Could not fetch invoices: {e}")
        return []
    finally:
        conn.close()
