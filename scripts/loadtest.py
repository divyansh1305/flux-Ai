"""Load test for Kitna – realistic traffic mix against a real gunicorn server.

    # terminal 1
    SECRET_KEY=$(python -c 'import secrets;print(secrets.token_hex(32))') DATABASE_PATH=/tmp/flux-load.db \
      gunicorn -c gunicorn.conf.py "flux:create_app()"
    # terminal 2 (same SECRET_KEY + DATABASE_PATH so it can seed users and sign their session cookies)
    SECRET_KEY=... DATABASE_PATH=/tmp/flux-load.db python scripts/loadtest.py --users 200 --concurrency 32 --seconds 60

Each virtual user is a real account with ~6 months of history (≈180 transactions) and an ingest token.
Traffic mix per request (what the app + Android companion actually do):
    45%  GET  /api/dashboard           (heaviest read: balance, safe-to-spend, reconcile, budgets)
    15%  GET  /api/transactions
    20%  POST /api/ingest/notification (phone pushing a payment, with dedupe + snapshot)
    10%  POST /api/transactions        (manual / voice add, with CSRF)
    10%  GET  /api/insights            (recurring detection, cashback report)
Prints p50/p95/p99 per endpoint, throughput and error rate, and writes JSON to --out.
"""
import argparse
import hashlib
import http.client
import json
import os
import random
import secrets
import statistics
import sys
import threading
import time
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MERCHANTS = [("Zomato", "zomato@hdfcbank", "Food & Dining"), ("Swiggy", "swiggy@icici", "Food & Dining"),
             ("Uber", "uber@axis", "Transport"), ("BigBasket", "bigbasket@hdfc", "Groceries"),
             ("Amazon", "amazon@apl", "Shopping"), ("Airtel", "airtel@ybl", "Bills & Utilities"),
             ("Ramu Tea Stall", "ramu.tea@okaxis", "Food & Dining"), ("Netflix", "netflix@icici", "Entertainment")]


def seed(n_users):
    """Create users with history + tokens directly in the DB, return [(cookie, csrf, token)]."""
    from flask import Flask  # noqa: F401

    from flux import create_app
    from flux.db import get_db

    app = create_app()
    out = []
    with app.app_context():
        db = get_db()
        ser = app.session_interface.get_signing_serializer(app)
        today = date.today()
        rnd = random.Random(42)
        for i in range(n_users):
            email = f"load{i}@flux.test"
            row = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if row:
                uid = row["id"]
            else:
                uid = db.execute("INSERT INTO users (email, name, onboarded) VALUES (?,?,1)", (email, f"Load User{i}")).lastrowid
                gid = db.execute("INSERT INTO goals (user_id, title, target) VALUES (?,?,?)", (uid, "Emergency fund", 5000000)).lastrowid
                db.execute("UPDATE users SET autosave_goal_id = ? WHERE id = ?", (gid, uid))
                rows = []
                for m in range(6):
                    d0 = today - timedelta(days=30 * m)
                    rows.append((uid, "income", 4500000, "Salary", "Salary", (d0.replace(day=1)).isoformat(), "import"))
                    rows.append((uid, "expense", 1500000, "Rent", "Rent", (d0.replace(day=2)).isoformat(), "import"))
                    rows.append((uid, "expense", 64900, "Entertainment", "Netflix", (d0.replace(day=5)).isoformat(), "sms"))
                for _ in range(160):
                    name, _vpa, cat = rnd.choice(MERCHANTS)
                    d = today - timedelta(days=rnd.randint(0, 180))
                    rows.append((uid, "expense", rnd.randint(20, 1500) * 100, cat, name, d.isoformat(), "notification"))
                db.executemany("INSERT INTO transactions (user_id, kind, amount, category, note, date, source)"
                               " VALUES (?,?,?,?,?,?,?)", rows)
            token = "flx_" + secrets.token_urlsafe(32)
            db.execute("INSERT INTO ingest_tokens (user_id, token_hash) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE"
                       " SET token_hash = excluded.token_hash", (uid, hashlib.sha256(token.encode()).hexdigest()))
            csrf = secrets.token_urlsafe(32)
            cookie = ser.dumps({"uid": uid, "csrf": csrf, "_permanent": True})
            out.append((cookie, csrf, token))
        db.commit()
    return out


class Stats:
    def __init__(self):
        self.lat = defaultdict(list)
        self.codes = defaultdict(lambda: defaultdict(int))
        self.lock = threading.Lock()

    def add(self, name, ms, code):
        with self.lock:
            self.lat[name].append(ms)
            self.codes[name][code] += 1


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def worker(base, users, stats, stop_at, seq):
    u = urlparse(base)
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=30)
    rnd = random.Random()
    while time.time() < stop_at:
        cookie, csrf, token = rnd.choice(users)
        r = rnd.random()
        headers = {"Cookie": f"flux_session={cookie}", "X-Forwarded-For": f"10.0.{rnd.randint(0, 255)}.{rnd.randint(1, 254)}"}
        body = None
        if r < 0.45:
            name, method, path = "GET /api/dashboard", "GET", "/api/dashboard"
        elif r < 0.60:
            name, method, path = "GET /api/transactions", "GET", "/api/transactions"
        elif r < 0.80:
            m, vpa, _ = rnd.choice(MERCHANTS)
            amt = rnd.randint(20, 900)
            with seq[1]:
                seq[0] += 1
                n = seq[0]
            name, method, path = "POST /api/ingest/notification", "POST", "/api/ingest/notification"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            body = json.dumps({"package": "com.phonepe.app", "title": f"₹{amt} paid to {m}", "body": "",
                               "posted_at": int(time.time() * 1000) + n})
        elif r < 0.90:
            name, method, path = "POST /api/transactions", "POST", "/api/transactions"
            headers.update({"X-CSRF-Token": csrf, "Content-Type": "application/json"})
            body = json.dumps({"kind": "expense", "amount": rnd.randint(10, 500), "category": "Food & Dining", "note": "load chai"})
        else:
            name, method, path = "GET /api/insights", "GET", "/api/insights"
        t0 = time.perf_counter()
        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            resp.read()
            code = resp.status
        except Exception:
            code = 0
            conn.close()
            conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=30)
        stats.add(name, (time.perf_counter() - t0) * 1000, code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--users", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--out", default="docs/loadtest-results.json")
    a = ap.parse_args()

    t = time.time()
    users = seed(a.users)
    print(f"Seeded {len(users)} users in {time.time() - t:.1f}s")

    stats = Stats()
    stop_at = time.time() + a.seconds
    seq = [0, threading.Lock()]
    threads = [threading.Thread(target=worker, args=(a.base, users, stats, stop_at, seq)) for _ in range(a.concurrency)]
    t0 = time.time()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    elapsed = time.time() - t0

    total = sum(len(v) for v in stats.lat.values())
    errors = sum(n for c in stats.codes.values() for code, n in c.items() if code == 0 or code >= 500)
    allv = [x for v in stats.lat.values() for x in v]
    result = {"users": a.users, "concurrency": a.concurrency, "seconds": round(elapsed, 1), "requests": total,
              "rps": round(total / elapsed, 1), "error_rate": round(errors / max(total, 1), 5),
              "overall_ms": {"p50": round(pct(allv, 50), 1), "p95": round(pct(allv, 95), 1), "p99": round(pct(allv, 99), 1)},
              "endpoints": {}}
    print(f"\n{total} requests in {elapsed:.1f}s → {result['rps']} req/s, 5xx/conn errors: {errors}")
    print(f"{'endpoint':34} {'n':>6} {'p50':>7} {'p95':>7} {'p99':>7}  status codes")
    for name in sorted(stats.lat):
        v = stats.lat[name]
        e = {"n": len(v), "p50": round(pct(v, 50), 1), "p95": round(pct(v, 95), 1), "p99": round(pct(v, 99), 1),
             "mean": round(statistics.mean(v), 1), "codes": dict(stats.codes[name])}
        result["endpoints"][name] = e
        print(f"{name:34} {e['n']:>6} {e['p50']:>7} {e['p95']:>7} {e['p99']:>7}  {e['codes']}")
    print(f"{'ALL':34} {total:>6} {result['overall_ms']['p50']:>7} {result['overall_ms']['p95']:>7} {result['overall_ms']['p99']:>7}")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved {a.out}")


if __name__ == "__main__":
    main()
