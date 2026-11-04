"""SQLite connection handling (one connection per request) and versioned schema migrations.

    v1 -> v2  widen the `source` CHECK constraint (upi, sms, invest)
    v2 -> v3  add transactions.ref (bank/UPI reference) and the 'notification' source
SQLite can't alter a CHECK constraint, so the transactions table is rebuilt and rows copied.
"""
import os
import sqlite3

from flask import current_app, g

SCHEMA_VERSION = 5
# Columns added to existing tables after launch (ALTER TABLE ADD COLUMN is enough for these).
ADDED_COLUMNS = [
    ("users", "contribute_samples", "INTEGER NOT NULL DEFAULT 0"),
    # Money already in the account before Flux started tracking (paise). Set by "Match my bank".
    ("users", "opening_balance", "INTEGER NOT NULL DEFAULT 0"),
    # Personal safe-to-spend: when money comes in, roughly how much, and what to keep untouched.
    ("users", "income_pattern", "TEXT NOT NULL DEFAULT 'unset'"),   # unset | monthly | varies
    ("users", "pay_day", "INTEGER"),                               # 1-31 when income_pattern = monthly
    ("users", "expected_income", "INTEGER NOT NULL DEFAULT 0"),    # paise, optional
    ("users", "cushion", "INTEGER NOT NULL DEFAULT 0"),            # paise never counted as spendable
    ("users", "adult_confirmed", "INTEGER NOT NULL DEFAULT 0"),    # DPDP: Flux is for 18+ only
    ("gmail_accounts", "needs_reconnect", "INTEGER NOT NULL DEFAULT 0"),
]


def get_db():
    if "db" not in g:
        path = current_app.config["DATABASE"]
        if path != ":memory:":
            os.makedirs(os.path.dirname(path), exist_ok=True)
        conn = sqlite3.connect(path, detect_types=0, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        g.db = conn
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def init_db(app):
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with app.app_context():
        conn = get_db()
        if current_app.config["DATABASE"] != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")  # readers don't block the writer
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        old_cols = None
        if version < SCHEMA_VERSION and "transactions" in tables:
            old_cols = _columns(conn, "transactions")
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("ALTER TABLE transactions RENAME TO transactions_old")
            for idx in ("idx_tx_user_date", "idx_tx_import", "idx_tx_ref"):
                conn.execute(f"DROP INDEX IF EXISTS {idx}")
        with open(schema_path, encoding="utf-8") as f:
            conn.executescript(f.read())
        for table, column, decl in ADDED_COLUMNS:
            if column not in _columns(conn, table):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        if old_cols is not None:
            cols = ", ".join(c for c in _columns(conn, "transactions") if c in old_cols)
            conn.execute(f"INSERT INTO transactions ({cols}) SELECT {cols} FROM transactions_old")
            conn.execute("DROP TABLE transactions_old")
        if version < SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
    app.teardown_appcontext(close_db)
