"""Copy an existing Kitna database file (e.g. flux.db downloaded from PythonAnywhere) into Turso.

    TURSO_DATABASE_URL=libsql://... TURSO_AUTH_TOKEN=... python scripts/copy_to_turso.py path/to/flux.db

Run it once, on an empty Turso database, before people start using the Vercel site.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packages", "upi_parse", "src"))

from flux import create_app  # noqa: E402
from flux.db import get_db  # noqa: E402


def copy(src_path, app):
    src = sqlite3.connect(src_path)
    src.row_factory = sqlite3.Row
    with app.app_context():
        dst = get_db()   # tables are already created by create_app()
        dst.execute("PRAGMA foreign_keys = OFF")
        target_tables = {r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        done = {}
        for (table,) in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            if table not in target_tables:
                continue
            dst_cols = {r[1] for r in dst.execute(f"PRAGMA table_info({table})")}
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            n = 0
            for r in rows:
                cols = [k for k in r.keys() if k in dst_cols]
                dst.execute(f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                            [r[k] for k in cols])
                n += 1
                if n % 200 == 0:
                    dst.commit()
            dst.commit()
            done[table] = n
        dst.execute("PRAGMA foreign_keys = ON")
    return done


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.environ.get("TURSO_DATABASE_URL"):
        sys.exit(__doc__)
    for t, n in copy(sys.argv[1], create_app()).items():
        print(f"{t}: {n} rows")
