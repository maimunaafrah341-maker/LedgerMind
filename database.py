"""Local ledger (SQLite). Hindsight holds what the agent *knows*; this holds what was *posted*."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.environ.get("LEDGERMIND_DB", "ledgermind.db")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS reviews (
                workspace   TEXT NOT NULL,
                invoice_key TEXT NOT NULL,
                payload     TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                PRIMARY KEY (workspace, invoice_key)
            );
            CREATE TABLE IF NOT EXISTS postings (
                workspace   TEXT NOT NULL,
                invoice_key TEXT NOT NULL,
                vendor      TEXT NOT NULL,
                number      TEXT NOT NULL,
                total       REAL NOT NULL,
                verdict     TEXT NOT NULL,
                decision    TEXT NOT NULL,
                note        TEXT,
                at_risk     REAL NOT NULL DEFAULT 0,
                retained    TEXT,
                created_at  TEXT NOT NULL,
                PRIMARY KEY (workspace, invoice_key)
            );
        """)


def save_review(workspace, key, payload):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?,?)",
                  (workspace, key, json.dumps(payload), datetime.now().isoformat()))


def get_review(workspace, key):
    with _conn() as c:
        row = c.execute("SELECT payload FROM reviews WHERE workspace=? AND invoice_key=?",
                        (workspace, key)).fetchone()
    return json.loads(row["payload"]) if row else None


def save_posting(workspace, invoice, verdict, decision, note, at_risk, retained):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO postings VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (workspace, invoice["key"], invoice["vendor"], invoice["number"], invoice["total"],
                   verdict, decision, note, at_risk, retained, datetime.now().isoformat()))


def postings(workspace):
    with _conn() as c:
        rows = c.execute("SELECT * FROM postings WHERE workspace=? ORDER BY created_at", (workspace,)).fetchall()
    return [dict(r) for r in rows]


def clear_workspace(workspace):
    with _conn() as c:
        c.execute("DELETE FROM reviews WHERE workspace=?", (workspace,))
        c.execute("DELETE FROM postings WHERE workspace=?", (workspace,))
