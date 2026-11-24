"""Kitna Rent: rent collection for PG, hostel and flat owners.

The problem it solves: tenants pay the owner's own UPI ID from GPay, PhonePe, a parent's account or in cash.
The bank alert says "₹8,500 credited from R K SHARMA" and the owner has to work out whose rent that was,
who is still due, and chase them on WhatsApp. Payment-gateway apps fix this by putting a gateway in the
middle (fees, and tenants must use their link). Kitna doesn't: tenants keep paying the owner directly, and
Kitna reads the owner's bank alerts (Gmail / SMS, already connected for personal tracking) and matches them.

How a payment is matched (in order):
  1. A payer the owner already taught Kitna ("R K SHARMA is Rahul's father") → that tenant.
  2. The tenant's name, or a name the owner listed as paying for them, is in the bank alert → that tenant.
  3. Otherwise it waits under "Whose rent is this?" with the likely tenants first (same amount as what
     they owe). One tap assigns it, and Kitna remembers the payer for next month.

Balances are never stored: a tenant owes (old dues + rent for every month so far) − (everything they paid).
Payments are applied oldest month first, so "late since 5 Oct" is always worked out the same way.
"""
import re
import secrets
from datetime import date, timedelta

from . import clock
from .db import get_db
from .finance import merchant_key, rupees
from .friends import name_in
from .security import ApiError

FREE_TENANTS = 5            # Kitna Rent is free up to this many active tenants
RENT_CATEGORY = "Rent received"
NOT_RENT_CATEGORIES = ("Paid back", "Refund", "Cashback", "Interest", "Salary")
LOOKBACK_DAYS = 60          # how far back "Whose rent is this?" looks
MIN_RENT = 100_00           # credits under ₹100 are never rent


# ─── months ──────────────────────────────────────────────────
def month_of(d):
    return d.strftime("%Y-%m")


def months_from(start, end):
    """['2026-10', '2026-11', ...] inclusive."""
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em) and len(out) < 240:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def due_date(month, due_day):
    y, m = map(int, month.split("-"))
    return date(y, m, min(due_day, 28))


def valid_month(v, label="Month"):
    if not isinstance(v, str) or not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", v):
        raise ApiError(f"{label} must look like 2026-11.")
    return v


# ─── plan ────────────────────────────────────────────────────
def is_pro(user):
    until = user["plan_until"] if "plan_until" in user.keys() else None
    return bool(until) and until >= clock.today().isoformat()


# ─── property ────────────────────────────────────────────────
def get_property(user_id):
    return get_db().execute("SELECT * FROM rent_properties WHERE user_id = ? ORDER BY id LIMIT 1", (user_id,)).fetchone()


def save_property(user_id, name, upi_id, due_day):
    db = get_db()
    p = get_property(user_id)
    if p:
        db.execute("UPDATE rent_properties SET name = ?, upi_id = ?, due_day = ? WHERE id = ?", (name, upi_id, due_day, p["id"]))
    else:
        db.execute("INSERT INTO rent_properties (user_id, name, upi_id, due_day) VALUES (?,?,?,?)", (user_id, name, upi_id, due_day))
    db.commit()
    return get_property(user_id)


def property_json(p):
    return {"id": p["id"], "name": p["name"], "upi_id": p["upi_id"], "due_day": p["due_day"]} if p else None


# ─── tenants ─────────────────────────────────────────────────
def active_count(user_id):
    return get_db().execute("SELECT COUNT(*) FROM rent_tenants WHERE user_id = ? AND status = 'active'", (user_id,)).fetchone()[0]


def add_tenant(user, data, commit=True):
    p = get_property(user["id"])
    if not p:
        raise ApiError("Set up your PG or flat first.")
    if not is_pro(user) and active_count(user["id"]) >= FREE_TENANTS:
        raise ApiError(f"The free plan covers {FREE_TENANTS} tenants. Upgrade to Kitna Rent Pro to add more.", 402)
    db = get_db()
    cur = db.execute(
        "INSERT INTO rent_tenants (user_id, property_id, name, phone, room, rent, payer_names, start_month, opening_due, token)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (user["id"], p["id"], data["name"], data.get("phone", ""), data.get("room", ""), data["rent"],
         data.get("payer_names", ""), data.get("start_month") or month_of(clock.today()), data.get("opening_due", 0),
         secrets.token_urlsafe(12)))
    if commit:
        db.commit()
    return cur.lastrowid


def get_tenant(user_id, tenant_id):
    t = get_db().execute("SELECT * FROM rent_tenants WHERE id = ? AND user_id = ?", (tenant_id, user_id)).fetchone()
    if t is None:
        raise ApiError("Tenant not found.", 404)
    return t


def payments_of(tenant_id):
    return get_db().execute("SELECT * FROM rent_payments WHERE tenant_id = ? ORDER BY date, id", (tenant_id,)).fetchall()


def state(t, due_day, today=None, payments=None):
    """Where one tenant stands today. Pure arithmetic over months and payments."""
    today = today or clock.today()
    now = month_of(today)
    last = min(now, t["left_month"]) if t["status"] == "left" and t["left_month"] else now
    months = months_from(t["start_month"], last) if t["start_month"] <= last else []
    pays = payments if payments is not None else payments_of(t["id"])
    paid = sum(p["amount"] for p in pays)
    # What was owed, oldest first: old dues, then each month's rent.
    owed = [("before", None, t["opening_due"])] if t["opening_due"] else []
    owed += [(m, due_date(m, due_day), t["rent"]) for m in months]
    total = sum(a for _, _, a in owed)
    left = paid
    month_rows, oldest_unpaid = [], None
    for m, dd, amt in owed:
        cover = min(left, amt)
        left -= cover
        if cover < amt and oldest_unpaid is None:
            oldest_unpaid = (m, dd)
        if m != "before":
            month_rows.append({"month": m, "due_date": dd.isoformat(), "rent": rupees(amt), "paid": rupees(cover),
                               "status": "paid" if cover >= amt else "part" if cover else "due"})
    balance = total - paid
    if balance <= 0:
        status, late_days, due_on = "paid", 0, None
    else:
        dd = oldest_unpaid[1] if oldest_unpaid and oldest_unpaid[1] else (due_date(now, due_day))
        late_days = max(0, (today - dd).days)
        status = "late" if late_days > 0 else "due"
        due_on = dd.isoformat()
    return {"balance": rupees(balance), "money": status, "late_days": late_days, "due_on": due_on,
            "advance": rupees(-balance) if balance < 0 else 0, "months": month_rows[-12:][::-1],
            "paid_total": rupees(paid)}


def tenant_json(t, st, base_url=""):
    return {"id": t["id"], "name": t["name"], "phone": t["phone"], "room": t["room"], "rent": rupees(t["rent"]),
            "payer_names": t["payer_names"], "start_month": t["start_month"], "opening_due": rupees(t["opening_due"]),
            "status": t["status"], "left_month": t["left_month"], "link": f"{base_url}/r/{t['token']}", **st}


ORDER = {"late": 0, "due": 1, "paid": 2}


def overview(user, base_url=""):
    uid = user["id"]
    p = get_property(uid)
    if not p:
        return {"property": None, "tenants": [], "plan": plan_json(user)}
    db = get_db()
    today = clock.today()
    tenants = db.execute("SELECT * FROM rent_tenants WHERE user_id = ? ORDER BY status, name", (uid,)).fetchall()
    pays = {}
    for r in db.execute("SELECT * FROM rent_payments WHERE user_id = ? ORDER BY date, id", (uid,)):
        pays.setdefault(r["tenant_id"], []).append(r)
    rows = []
    for t in tenants:
        st = state(t, p["due_day"], today, pays.get(t["id"], []))
        if t["status"] == "left" and st["balance"] <= 0:
            continue
        rows.append(tenant_json(t, st, base_url))
    rows.sort(key=lambda r: (r["status"] != "active", ORDER[r["money"]], -r["late_days"], r["name"].lower()))
    month = month_of(today)
    expected = sum(t["rent"] for t in tenants if t["status"] == "active" and t["start_month"] <= month)
    collected = db.execute("SELECT COALESCE(SUM(amount),0) FROM rent_payments WHERE user_id = ? AND substr(date,1,7) = ?",
                           (uid, month)).fetchone()[0]
    counts = {"late": 0, "due": 0, "paid": 0}
    for r in rows:
        counts[r["money"]] += 1
    pending = sum(max(0, r["balance"]) for r in rows)
    return {"property": property_json(p), "tenants": rows, "month": month,
            "expected": rupees(expected), "collected": rupees(collected), "pending": round(pending, 2),
            "counts": counts, "unmatched": unmatched(uid, rows), "plan": plan_json(user)}


def plan_json(user):
    pro = is_pro(user)
    used = active_count(user["id"])
    return {"pro": pro, "until": user["plan_until"] if pro else None, "free_tenants": FREE_TENANTS,
            "tenants": used, "at_limit": (not pro) and used >= FREE_TENANTS}


# ─── matching money in to tenants ────────────────────────────
def _payer_key(note):
    key = merchant_key(note)
    return key if len(key) >= 3 else ""


def match_payment(user_id, tx_id, amount, note, day):
    """Called for every new income. Logs it as rent if Kitna can tell whose it is. Never commits."""
    db = get_db()
    if amount < MIN_RENT:
        return None
    tenants = db.execute("SELECT * FROM rent_tenants WHERE user_id = ? AND status = 'active'", (user_id,)).fetchall()
    if not tenants:
        return None
    tenant = None
    key = _payer_key(note)
    if key:
        r = db.execute("SELECT tenant_id FROM rent_payers WHERE user_id = ? AND payer_key = ?", (user_id, key)).fetchone()
        if r:
            tenant = next((t for t in tenants if t["id"] == r["tenant_id"]), None)
    if tenant is None:
        named = [t for t in tenants if _mentions(t["name"], note) or any(_mentions(n, note) for n in _names(t["payer_names"]))]
        if len(named) == 1:
            tenant = named[0]
    if tenant is None:
        return None
    _record(user_id, tenant["id"], amount, day, "upi", "auto", tx_id)
    from .analytics import track

    track(user_id, "rent_marked", "auto")
    return tenant


def _mentions(person, note):
    """'Rahul Verma' in 'RAHUL K VERMA' or in a UPI handle like 'rahulverma@okhdfc' / 'vermarahul99'."""
    if name_in(person, note):
        return True
    compact = re.sub(r"[^a-z]", "", (note or "").lower())
    parts = [w for w in re.findall(r"[a-z]+", person.lower()) if len(w) >= 4]
    return bool(parts) and all(w in compact for w in parts[:2])


def _names(text):
    return [n.strip() for n in re.split(r"[,;/]", text or "") if n.strip()]


def _record(user_id, tenant_id, amount, day, method, how, tx_id=None):
    db = get_db()
    db.execute("INSERT INTO rent_payments (user_id, tenant_id, amount, date, method, how, transaction_id) VALUES (?,?,?,?,?,?,?)",
               (user_id, tenant_id, amount, day, method, how, tx_id))
    if tx_id:
        db.execute("UPDATE transactions SET category = ?, needs_review = 0 WHERE id = ? AND user_id = ?", (RENT_CATEGORY, tx_id, user_id))


def unmatched(user_id, tenant_rows):
    """Money that came in recently and may be rent nobody has claimed yet, with likely tenants first."""
    if not tenant_rows:
        return []
    since = (clock.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    marks = ",".join("?" * len(NOT_RENT_CATEGORIES))
    rows = get_db().execute(
        f"SELECT t.* FROM transactions t WHERE t.user_id = ? AND t.kind = 'income' AND t.date >= ? AND t.amount >= ?"
        f" AND t.category NOT IN ({marks})"
        " AND NOT EXISTS (SELECT 1 FROM rent_payments p WHERE p.transaction_id = t.id)"
        " AND NOT EXISTS (SELECT 1 FROM rent_not_rent n WHERE n.transaction_id = t.id AND n.user_id = t.user_id)"
        " ORDER BY t.date DESC, t.id DESC LIMIT 20", (user_id, since, MIN_RENT, *NOT_RENT_CATEGORIES)).fetchall()
    active = [r for r in tenant_rows if r["status"] == "active"]
    out = []
    for r in rows:
        amt = rupees(r["amount"])
        likely = [t for t in active if abs(t["balance"] - amt) < 1 or abs(t["rent"] - amt) < 1]
        rest = sorted((t for t in active if t not in likely), key=lambda t: -t["balance"])
        out.append({"transaction_id": r["id"], "amount": amt, "date": r["date"], "note": r["note"],
                    "likely": [t["id"] for t in likely],
                    "choices": [{"id": t["id"], "name": t["name"], "room": t["room"]} for t in (likely + rest)[:8]]})
    return out


def assign(user_id, tx_id, tenant_id):
    db = get_db()
    tx = db.execute("SELECT * FROM transactions WHERE id = ? AND user_id = ? AND kind = 'income'", (tx_id, user_id)).fetchone()
    if tx is None:
        raise ApiError("Payment not found.", 404)
    get_tenant(user_id, tenant_id)
    if db.execute("SELECT 1 FROM rent_payments WHERE transaction_id = ?", (tx_id,)).fetchone():
        raise ApiError("This payment is already counted as rent.", 409)
    _record(user_id, tenant_id, tx["amount"], tx["date"], "upi", "tapped", tx_id)
    key = _payer_key(tx["note"])
    if key:
        db.execute("INSERT INTO rent_payers (user_id, payer_key, tenant_id) VALUES (?,?,?)"
                   " ON CONFLICT(user_id, payer_key) DO UPDATE SET tenant_id = excluded.tenant_id", (user_id, key, tenant_id))
    db.commit()


def not_rent(user_id, tx_id):
    db = get_db()
    if db.execute("SELECT 1 FROM transactions WHERE id = ? AND user_id = ?", (tx_id, user_id)).fetchone() is None:
        raise ApiError("Payment not found.", 404)
    db.execute("INSERT OR IGNORE INTO rent_not_rent (user_id, transaction_id) VALUES (?,?)", (user_id, tx_id))
    db.commit()


def record_manual(user_id, tenant_id, amount, day, method):
    get_tenant(user_id, tenant_id)
    if method not in ("cash", "bank", "upi"):
        raise ApiError("How was it paid?")
    _record(user_id, tenant_id, amount, day, method, "manual")
    get_db().commit()


def delete_payment(user_id, payment_id):
    db = get_db()
    p = db.execute("SELECT * FROM rent_payments WHERE id = ? AND user_id = ?", (payment_id, user_id)).fetchone()
    if p is None:
        raise ApiError("Payment not found.", 404)
    db.execute("DELETE FROM rent_payments WHERE id = ?", (payment_id,))
    if p["transaction_id"]:
        db.execute("UPDATE transactions SET category = 'Other Income' WHERE id = ? AND user_id = ? AND category = ?",
                   (p["transaction_id"], user_id, RENT_CATEGORY))
    db.commit()


# ─── reminders and the tenant's own page ─────────────────────
def wa_phone(phone):
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        return "91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    return ""


def remind_text(p, t, st, link, lang="en"):
    first = t["name"].split(" ")[0]
    amt = f"₹{st['balance']:,.0f}"
    if lang == "hinglish":
        msg = f"Namaste {first}, {p['name']} ka rent {amt} baaki hai."
        if p["upi_id"]:
            msg += f" UPI: {p['upi_id']}."
        return msg + f" Details aur receipts: {link}"
    msg = f"Hi {first}, a gentle reminder: {amt} rent is due for {p['name']}."
    if st["money"] == "late":
        msg = f"Hi {first}, your rent of {amt} for {p['name']} is {st['late_days']} day{'s' if st['late_days'] != 1 else ''} late."
    if p["upi_id"]:
        msg += f" Please pay to UPI ID {p['upi_id']}."
    return msg + f" Your dues and receipts: {link}"


def by_token(token):
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{10,40}", token):
        return None
    return get_db().execute("SELECT * FROM rent_tenants WHERE token = ?", (token,)).fetchone()


def public_view(t):
    """What the tenant sees on their link: no other tenant, nothing about the owner except name and UPI ID."""
    db = get_db()
    p = db.execute("SELECT * FROM rent_properties WHERE id = ?", (t["property_id"],)).fetchone()
    pays = payments_of(t["id"])
    st = state(t, p["due_day"], payments=pays)
    return {"property": p["name"], "upi_id": p["upi_id"], "tenant": t["name"], "room": t["room"],
            "rent": rupees(t["rent"]), "due_day": p["due_day"], **st,
            "payments": [{"id": x["id"], "amount": rupees(x["amount"]), "date": x["date"], "method": x["method"]}
                         for x in reversed(pays)][:24]}


def upi_qr_link(upi_id, name, amount):
    from urllib.parse import quote

    q = f"pa={quote(upi_id, safe='@.-_')}&pn={quote(name)}&cu=INR"
    if amount and amount > 0:
        q += f"&am={amount:.2f}"
    return "upi://pay?" + q
