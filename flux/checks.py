"""Money checks: real problems Kitna can spot in a user's own payments, shown only to that user.

  * Failed payment watch - the bank said a payment failed, so money may have left the account and must
    come back. RBI's failed-transaction rules (TAT circular, 2019): a failed UPI transfer is reversed by
    T+1 and a failed payment to a shop by T+5; after that the bank owes Rs 100 per day.
  * Charged twice - same merchant, same amount, same day, two different bank references.
  * Price went up - a regular monthly payment now costs more than last time.

Every check can be dismissed, and a dismissed check never comes back.
"""
import hashlib
import re
import statistics
from datetime import date, timedelta

from . import clock
from .db import get_db
from .finance import merchant_key, rupees

FAILED_RE = re.compile(r"\b(failed|declined|unsuccessful|could not be processed|not successful)\b", re.I)
MONEY_LEFT_RE = re.compile(r"\b(debited|deducted|amount (?:has been |was )?(?:debited|deducted)|will be (?:reversed|refunded|credited back)|"
                           r"reversal|refund)\b", re.I)
SKIP_RE = re.compile(r"\b(otp|one[- ]time password|login|mandate (?:creation|setup)|request)\b", re.I)
REF_RE = re.compile(r"\b(?:ref(?:erence)?|rrn|utr|txn)\s*(?:no\.?|number|id)?\s*(?:is)?\s*[:#-]?\s*(\d{9,16})", re.I)


def _amount(text):
    from upi_parse._common import find_amount

    a = find_amount(text)
    return round(float(a) * 100) if a is not None else None


def detect_failed(user_id, text, received_on=None):
    """If this bank message says a payment failed after money was taken, start watching for the refund.
    Returns the watch id, or None. Safe to call for every message that wasn't a normal transaction."""
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) < 20 or not FAILED_RE.search(t) or SKIP_RE.search(t) or not MONEY_LEFT_RE.search(t):
        return None
    amount = _amount(t)
    if not amount or amount <= 0:
        return None
    day = (received_on or clock.today()).isoformat()
    ref = REF_RE.search(t)
    ref = ref.group(1) if ref else None
    note = ""
    m = re.search(r"\bto\s+(?:vpa\s+)?([A-Za-z0-9@._ -]{3,40}?)(?:\s+(?:on|ref|has|is|was|failed|for)\b|[.,]|$)", t, re.I)
    if m:
        note = m.group(1).strip()
    fp = hashlib.sha256(f"{user_id}|{ref or ''}|{amount}|{day if not ref else ''}".encode()).hexdigest()[:32]
    db = get_db()
    cur = db.execute("INSERT OR IGNORE INTO refund_watch (user_id, amount, date, note, ref, fingerprint) VALUES (?,?,?,?,?,?)",
                     (user_id, amount, day, note[:60], ref, fp))
    if cur.rowcount:
        return cur.lastrowid
    old = db.execute("SELECT id FROM refund_watch WHERE user_id = ? AND fingerprint = ?", (user_id, fp)).fetchone()
    return old["id"] if old else None  # the same failed-payment message again: already being watched


def resolve_by_refund(user_id, amount_paise, day):
    """A refund/reversal credit arrived: close the oldest open watch with the same amount (within 15 days)."""
    since = (date.fromisoformat(day) - timedelta(days=15)).isoformat()
    db = get_db()
    row = db.execute("SELECT id FROM refund_watch WHERE user_id = ? AND status = 'open' AND amount = ? AND date >= ?"
                     " ORDER BY date LIMIT 1", (user_id, amount_paise, since)).fetchone()
    if row:
        db.execute("UPDATE refund_watch SET status = 'back' WHERE id = ?", (row["id"],))
        from .analytics import track

        track(user_id, "refund_back")
        return row["id"]
    return None


def _dismissed(user_id):
    return {r["check_key"] for r in get_db().execute("SELECT check_key FROM dismissed_checks WHERE user_id = ?", (user_id,))}


def dismiss(user_id, key):
    from .analytics import track

    db = get_db()
    kind = key.split(":")[0]
    if key.startswith("refund:"):
        status = "back" if key.endswith(":back") else "ignored"
        wid = key.split(":")[1]
        db.execute("UPDATE refund_watch SET status = ? WHERE id = ? AND user_id = ?", (status, wid, user_id))
        track(user_id, "refund_back" if status == "back" else "check_dismissed", "" if status == "back" else "refund")
    else:
        track(user_id, "check_dismissed", {"double": "double", "price": "price"}.get(kind, "other"))
        db.execute("INSERT OR IGNORE INTO dismissed_checks (user_id, check_key) VALUES (?,?)", (user_id, key[:120]))
    db.commit()


def _fmt(d):
    return date.fromisoformat(d).strftime("%-d %b") if isinstance(d, str) else d.strftime("%-d %b")


def refund_checks(user_id):
    today = clock.today()
    out = []
    for w in get_db().execute("SELECT * FROM refund_watch WHERE user_id = ? AND status = 'open' AND date >= ? ORDER BY date",
                              (user_id, (today - timedelta(days=45)).isoformat())):
        d = date.fromisoformat(w["date"])
        transfer_by, shop_by = d + timedelta(days=1), d + timedelta(days=5)
        late = today > shop_by
        to = f" to {w['note']}" if w["note"] else ""
        body = (f"Your bank said this payment failed. If the money left your account, it must come back: by {_fmt(transfer_by)} "
                f"for a UPI transfer to a person, or by {_fmt(shop_by)} for a payment to a shop. ")
        body += ("It's past that date: ask your bank for the reversal and the ₹100-a-day delay compensation under RBI rules."
                 if late else "Kitna closes this by itself when the refund SMS or email arrives.")
        out.append({"key": f"refund:{w['id']}", "type": "refund", "level": "caution" if late else "info",
                    "title": f"Watching ₹{rupees(w['amount']):,.0f}{to} from {_fmt(d)}", "body": body,
                    "ref": w["ref"], "actions": [{"label": "It's back", "key": f"refund:{w['id']}:back"},
                                                 {"label": "Not needed", "key": f"refund:{w['id']}:ignore"}]})
    return out


def double_charges(user_id, days=14):
    """Same merchant + same amount + same day, with two different bank references (so it isn't one payment
    seen twice). Only for amounts of ₹200+, since two ₹20 chais on one day are normal."""
    since = (clock.today() - timedelta(days=days)).isoformat()
    rows = get_db().execute(
        "SELECT id, note, amount, date, ref FROM transactions WHERE user_id = ? AND kind = 'expense' AND date >= ?"
        " AND amount >= 20000 AND ref IS NOT NULL ORDER BY date, id", (user_id, since)).fetchall()
    groups = {}
    for r in rows:
        groups.setdefault((merchant_key(r["note"]), r["amount"], r["date"]), []).append(r)
    out = []
    for (mk, amount, day), items in groups.items():
        if not mk or len({i["ref"] for i in items}) < 2:
            continue
        name = items[0]["note"]
        out.append({"key": f"double:{items[0]['id']}:{items[1]['id']}", "type": "double", "level": "caution",
                    "title": f"Charged twice? ₹{rupees(amount):,.0f} to {name} on {_fmt(day)}",
                    "body": f"Kitna saw {len(items)} payments of the same amount to {name} on the same day, with different bank "
                            "references. If you only paid once, ask the merchant or your bank for a refund.",
                    "actions": [{"label": "That's right", "key": f"double:{items[0]['id']}:{items[1]['id']}"}]})
    return out


def price_rises(user_id, lookback_days=120):
    """A payment that repeats roughly monthly now costs at least 5% (and ₹10) more than the time before."""
    today = clock.today()
    rows = get_db().execute(
        "SELECT note, amount, date FROM transactions WHERE user_id = ? AND kind = 'expense' AND date >= ?"
        " AND category NOT IN ('Transfers','Rent') ORDER BY date", (user_id, (today - timedelta(days=lookback_days)).isoformat())).fetchall()
    groups = {}
    for r in rows:
        k = merchant_key(r["note"])
        if k:
            groups.setdefault(k, []).append(r)
    out = []
    for k, items in groups.items():
        if len(items) < 2:
            continue
        dates = [date.fromisoformat(i["date"]) for i in items]
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        if not gaps or not 25 <= statistics.median(gaps) <= 35:
            continue
        prev, last = items[-2]["amount"], items[-1]["amount"]
        if last - prev >= 1000 and last >= prev * 1.05 and last <= prev * 2 and (today - dates[-1]).days <= 40:
            name = items[-1]["note"]
            out.append({"key": f"price:{k}:{last}", "type": "price", "level": "info",
                        "title": f"{name} went up: ₹{rupees(prev):,.0f} → ₹{rupees(last):,.0f}",
                        "body": f"That's ₹{rupees((last - prev) * 12):,.0f} more a year. Still worth it? If not, cancel it in the app or website you subscribed from.",
                        "actions": [{"label": "Okay", "key": f"price:{k}:{last}"}]})
    return out


def all_checks(user_id):
    hidden = _dismissed(user_id)
    found = [c for c in refund_checks(user_id) + double_charges(user_id) + price_rises(user_id) if c["key"] not in hidden]
    if found:  # count each check once, the first time it is shown
        from .analytics import track

        db = get_db()
        for c in found:
            if db.execute("INSERT OR IGNORE INTO seen_checks (user_id, check_key) VALUES (?,?)", (user_id, c["key"][:120])).rowcount:
                track(user_id, "check_found", c["type"])
        db.commit()
    return found
