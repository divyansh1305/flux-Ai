"""Money between you and friends: "Rahul owes me ₹500 for dinner" or "I owe Priya ₹300".

How it stays automatic:
  * Split a payment you made → one "they owe" row per friend, linked to that payment. Your budgets and
    "spent this month" then count only your share; your balance stays what the bank has.
  * When money comes in (SMS, Gmail, Android notification, statement or by hand) Kitna looks at the open rows:
      - same amount (±₹1) AND the friend's name is in the payment → ticked off by itself, filed as "Paid back";
      - same amount but no name (some banks hide it) → Kitna asks "Was this from Rahul?" instead of guessing.
  * Money you send to a friend you owe is matched the same way.
"""
import re
from datetime import date, timedelta

from . import clock
from .db import get_db
from .finance import rupees
from .security import ApiError

PAID_BACK = "Paid back"
MATCH_WINDOW_DAYS = 120
_STOP = {"mr", "mrs", "ms", "shri", "smt", "the", "and", "kumar", "bhai", "bro", "upi", "from", "to", "paid"}


def _tokens(text):
    return {t for t in re.findall(r"[a-zऀ-ॿ]+", str(text or "").lower()) if len(t) >= 3 and t not in _STOP}


def name_in(person, text):
    """Does the payment's text mention this friend? First name or any longer part of the name is enough."""
    words = _tokens(person)
    return bool(words) and bool(words & _tokens(text))


def row_json(r):
    return {"id": r["id"], "direction": r["direction"], "person": r["person"], "amount": rupees(r["amount"]),
            "note": r["note"], "date": r["date"], "transaction_id": r["transaction_id"],
            "settled": r["settled_at"] is not None, "settled_at": r["settled_at"],
            "suggested_tx_id": r["suggested_tx_id"]}


def add(user_id, person, amount, note="", direction="they_owe", day=None, transaction_id=None, commit=True):
    person = re.sub(r"\s+", " ", str(person or "")).strip()[:40]
    if not person:
        raise ApiError("Add the friend's name.")
    if direction not in ("they_owe", "i_owe"):
        raise ApiError("Bad direction.")
    if not isinstance(amount, int) or amount <= 0:
        raise ApiError("Enter an amount above ₹0.")
    db = get_db()
    cur = db.execute("INSERT INTO owed (user_id, direction, person, amount, note, date, transaction_id) VALUES (?,?,?,?,?,?,?)",
                     (user_id, direction, person, amount, str(note or "")[:80], day or clock.today().isoformat(),
                      transaction_id))
    if commit:
        db.commit()
    return cur.lastrowid


def split(user_id, tx_id, people):
    """people = [{"name": "Rahul", "amount": paise}, ...]. Your own share is whatever is left."""
    db = get_db()
    tx = db.execute("SELECT * FROM transactions WHERE id = ? AND user_id = ? AND kind = 'expense'", (tx_id, user_id)).fetchone()
    if tx is None:
        raise ApiError("Payment not found.", 404)
    if not isinstance(people, list) or not 1 <= len(people) <= 20:
        raise ApiError("Add between 1 and 20 friends.")
    already = db.execute("SELECT COALESCE(SUM(amount),0) FROM owed WHERE user_id = ? AND transaction_id = ? AND direction='they_owe'",
                         (user_id, tx_id)).fetchone()[0]
    total = sum(p.get("amount", 0) for p in people if isinstance(p, dict))
    if already + total > tx["amount"]:
        raise ApiError(f"Friends' shares add up to more than the ₹{rupees(tx['amount']):,.0f} you paid.")
    ids = []
    try:
        for p in people:
            if not isinstance(p, dict):
                raise ApiError("Bad friend.")
            ids.append(add(user_id, p.get("name"), p.get("amount"), tx["note"] or tx["category"], "they_owe", tx["date"],
                           tx_id, commit=False))
        db.commit()
    except Exception:
        db.rollback()
        raise
    from .analytics import track

    track(user_id, "split_added", "")
    return ids


def settle(user_id, owed_id, tx_id=None):
    db = get_db()
    r = db.execute("SELECT * FROM owed WHERE id = ? AND user_id = ?", (owed_id, user_id)).fetchone()
    if r is None:
        raise ApiError("Not found.", 404)
    if r["settled_at"] is None:
        if tx_id is not None:
            tx = db.execute("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (tx_id, user_id)).fetchone()
            if tx is None:
                raise ApiError("Payment not found.", 404)
            if r["direction"] == "they_owe" and tx["kind"] == "income":
                db.execute("UPDATE transactions SET category = ? WHERE id = ?", (PAID_BACK, tx_id))
        db.execute("UPDATE owed SET settled_at = datetime('now'), settled_tx_id = ?, suggested_tx_id = NULL WHERE id = ?",
                   (tx_id, owed_id))
        db.commit()
        from .analytics import track

        track(user_id, "owed_settled", "auto" if tx_id else "manual")
    return row_json(db.execute("SELECT * FROM owed WHERE id = ?", (owed_id,)).fetchone())


def not_them(user_id, owed_id):
    """'No, that payment wasn't from Rahul': forget the suggestion."""
    get_db().execute("UPDATE owed SET suggested_tx_id = NULL WHERE id = ? AND user_id = ?", (owed_id, user_id))
    get_db().commit()


def delete(user_id, owed_id):
    get_db().execute("DELETE FROM owed WHERE id = ? AND user_id = ?", (owed_id, user_id))
    get_db().commit()


def match_payment(user_id, tx_id, kind, amount, text, day):
    """Called for every new income/expense. Returns the owed row it closed, or None. Never commits by itself."""
    direction = "they_owe" if kind == "income" else "i_owe" if kind == "expense" else None
    if direction is None:
        return None
    db = get_db()
    start = (date.fromisoformat(day) - timedelta(days=MATCH_WINDOW_DAYS)).isoformat()
    rows = db.execute(
        "SELECT * FROM owed WHERE user_id = ? AND direction = ? AND settled_at IS NULL AND date <= ? AND date >= ?"
        " AND ABS(amount - ?) <= 100 AND (transaction_id IS NULL OR transaction_id != ?) ORDER BY date, id",
        (user_id, direction, day, start, amount, tx_id)).fetchall()
    if not rows:
        return None
    named = [r for r in rows if name_in(r["person"], text)]
    if named:
        r = named[0]
        db.execute("UPDATE owed SET settled_at = datetime('now'), settled_tx_id = ?, suggested_tx_id = NULL WHERE id = ?",
                   (tx_id, r["id"]))
        if kind == "income":
            db.execute("UPDATE transactions SET category = ? WHERE id = ?", (PAID_BACK, tx_id))
        from .analytics import track

        track(user_id, "owed_settled", "auto")
        return r
    if kind == "income":  # amount matches but the bank didn't say who: ask, don't guess
        r = next((x for x in rows if x["suggested_tx_id"] is None), None)
        if r is not None:
            db.execute("UPDATE owed SET suggested_tx_id = ? WHERE id = ?", (tx_id, r["id"]))
    return None


def items(user_id, include_settled=False):
    sql = "SELECT * FROM owed WHERE user_id = ?" + ("" if include_settled else " AND settled_at IS NULL")
    sql += " ORDER BY settled_at IS NOT NULL, date DESC, id DESC LIMIT 300"
    return [row_json(r) for r in get_db().execute(sql, (user_id,))]


def totals(user_id):
    rows = get_db().execute(
        "SELECT direction, COUNT(*) AS n, COALESCE(SUM(amount),0) AS total, COUNT(DISTINCT lower(person)) AS people"
        " FROM owed WHERE user_id = ? AND settled_at IS NULL GROUP BY direction", (user_id,)).fetchall()
    by = {r["direction"]: r for r in rows}
    they, me = by.get("they_owe"), by.get("i_owe")
    return {"they_owe": rupees(they["total"]) if they else 0, "they_owe_people": they["people"] if they else 0,
            "i_owe": rupees(me["total"]) if me else 0, "i_owe_people": me["people"] if me else 0,
            "i_owe_paise": me["total"] if me else 0}


def suggestions(user_id):
    """Open rows where a payment of the same amount arrived without a name."""
    out = []
    for r in get_db().execute(
            "SELECT o.*, t.note AS tx_note, t.date AS tx_date FROM owed o JOIN transactions t ON t.id = o.suggested_tx_id"
            " WHERE o.user_id = ? AND o.settled_at IS NULL", (user_id,)):
        out.append({**row_json(r), "tx_note": r["tx_note"], "tx_date": r["tx_date"]})
    return out


def remind_message(user, r, lang="en"):
    """A friendly message the user can send on WhatsApp. Includes their UPI ID if they saved one."""
    first = r["person"].split(" ")[0]
    amount = f"₹{rupees(r['amount']):,.0f}"
    what = f" for {r['note']}" if r["note"] else ""
    upi = user["upi_id"] if user is not None and "upi_id" in user.keys() else None
    when = date.fromisoformat(r["date"]).strftime("%-d %b")
    if lang == "hinglish":
        msg = f"Hi {first}, {r['note'] or when} ke {amount} bhej dena jab time mile 🙂"
        if upi:
            msg += f" Mera UPI: {upi}"
    else:
        msg = f"Hi {first}, could you send me the {amount}{what} from {when} when you get a moment? 🙂"
        if upi:
            msg += f" My UPI ID: {upi}"
    return msg

