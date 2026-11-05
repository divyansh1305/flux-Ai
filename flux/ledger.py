"""Ledger integrity: cross-source de-duplication, bank-balance reconciliation, double-entry check.

1. De-duplication
   The same payment can reach Kitna up to four ways: Scan & Pay, the bank's SMS, the UPI app's
   notification, and later the bank statement. `find_duplicate` recognises it:
     • exact:  same bank/UPI reference number (UTR/RRN)
     • fuzzy:  same direction + amount, logged from a *different* source within a short window
2. Reconciliation
   Banks report "Avl Bal" in many SMS. Between two such reports, the change in the bank's
   balance must equal the net of everything Kitna logged in between. If not, Kitna is missing
   a transaction (and we can say roughly how much).
3. Double-entry projection
   Every Kitna record is projected into balanced journal lines (bank, goals, investments,
   income, expense accounts). The trial balance must sum to zero, and the bank-minus-earmarks
   figure must equal the app's "available" balance. Tests assert both invariants.
"""
from datetime import timedelta

from . import clock
from .db import get_db
from .finance import balance as available_balance
from .finance import rupees

AUTO_SOURCES = ("sms", "upi", "notification", "import")


# UPI apps the payer uses. A payment appears in exactly one of these, plus the bank's channels
# (SMS, bank app, statement) and possibly Kitna itself (Scan & Pay, voice, manual).
PAYMENT_APPS = frozenset({
    "com.google.android.apps.nbu.paisa.user", "com.phonepe.app", "net.one97.paytm", "in.org.npci.upiapp",
    "in.amazon.mShop.android.shopping", "com.dreamplug.androidapp", "money.super.payments", "com.whatsapp",
})


def find_duplicate(user_id, kind, amount_paise, day, ref=None, source="sms", window_days=1, origin=None):
    """Return the id of an existing transaction that is the same real-world payment, or None.

    Fuzzy matches (same kind + amount within ±window days) only count when the existing record
    came from a *different origin* (another app/channel). Two ₹20 payments seen by the same app
    are two payments; ₹20 seen by GPay and by the bank SMS is one.
    """
    origin = origin or source
    db = get_db()
    if ref:
        row = db.execute("SELECT id FROM transactions WHERE user_id = ? AND ref = ?", (user_id, ref)).fetchone()
        if row:
            return row["id"]
    lo = (clock.today() if not day else _d(day)) - timedelta(days=window_days)
    hi = (clock.today() if not day else _d(day)) + timedelta(days=window_days)
    rows = db.execute(
        "SELECT id, ref, COALESCE(origin, source) AS origin FROM transactions"
        " WHERE user_id = ? AND kind = ? AND amount = ? AND date BETWEEN ? AND ?"
        " AND COALESCE(origin, source) != ? AND source IN ('sms','upi','notification','import','voice','manual','email')"
        " ORDER BY id DESC LIMIT 10",
        (user_id, kind, amount_paise, lo.isoformat(), hi.isoformat(), origin)).fetchall()
    for row in rows:
        if ref and row["ref"]:
            continue  # two different refs = two different payments
        if origin in PAYMENT_APPS and row["origin"] in PAYMENT_APPS:
            continue  # ₹100 on GPay and ₹100 on PhonePe are two payments – one payment never shows in two UPI apps
        return row["id"]
    return None


def _d(value):
    from datetime import date

    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def record_snapshot(user_id, balance_paise, day, source, account_last4=None, transaction_id=None):
    get_db().execute(
        "INSERT INTO balance_snapshots (user_id, account_last4, balance, transaction_id, observed_date, source)"
        " VALUES (?,?,?,?,?,?)", (user_id, account_last4, balance_paise, transaction_id, str(day)[:10], source))


def latest_bank_balance(user_id):
    row = get_db().execute("SELECT * FROM balance_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                           (user_id,)).fetchone()
    if not row:
        return None
    return {"balance": rupees(row["balance"]), "as_of": row["observed_date"], "account_last4": row["account_last4"],
            "source": row["source"]}


def reconcile(user_id):
    """Compare the two most recent bank-reported balances (same account) with what Kitna logged in between."""
    db = get_db()
    last = db.execute("SELECT * FROM balance_snapshots WHERE user_id = ? AND transaction_id IS NOT NULL"
                      " ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
    if not last:
        return {"status": "no_data", "message": "Kitna checks your balance against the bank once it has seen two bank SMS with a balance."}
    prev = db.execute(
        "SELECT * FROM balance_snapshots WHERE user_id = ? AND id < ? AND transaction_id IS NOT NULL"
        " AND COALESCE(account_last4,'') = COALESCE(?, '') ORDER BY id DESC LIMIT 1",
        (user_id, last["id"], last["account_last4"])).fetchone()
    if not prev:
        return {"status": "no_data", "message": "Waiting for one more bank SMS with a balance to start checking."}
    net = db.execute(
        "SELECT COALESCE(SUM(CASE kind WHEN 'income' THEN amount WHEN 'expense' THEN -amount ELSE 0 END),0)"
        " FROM transactions WHERE user_id = ? AND id > ? AND id <= ? AND source != 'invest'",
        (user_id, prev["transaction_id"], last["transaction_id"])).fetchone()[0]
    expected = prev["balance"] + net
    drift = last["balance"] - expected
    result = {"from": prev["observed_date"], "to": last["observed_date"], "bank_balance": rupees(last["balance"]),
              "expected": rupees(expected), "drift": rupees(drift), "account_last4": last["account_last4"]}
    if abs(drift) <= 100:  # ±₹1 tolerance for rounding
        return {**result, "status": "in_sync", "message": "Kitna matches your bank. Nothing is missing."}
    what = "money came in" if drift > 0 else "a payment"
    return {**result, "status": "drift",
            "message": f"Kitna is missing about ₹{abs(rupees(drift)):,.2f}: {what} between {prev['observed_date']} and "
                       f"{last['observed_date']} that Kitna didn't see. Add it or import that day's SMS."}


def journal(user_id):
    """Project every record into balanced double-entry lines: (account, amount_paise); debits +, credits −."""
    db = get_db()
    lines = []
    opening = db.execute("SELECT opening_balance FROM users WHERE id = ?", (user_id,)).fetchone()["opening_balance"]
    if opening:
        lines += [("opening", "assets:unallocated", opening), ("opening", "equity:opening_balance", -opening)]
    for t in db.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY id", (user_id,)):
        a = t["amount"]
        if t["kind"] == "income":
            lines += [(t["id"], "assets:unallocated", a), (t["id"], f"income:{t['category']}", -a)]
        elif t["kind"] == "expense":
            lines += [(t["id"], f"expense:{t['category']}", a), (t["id"], "assets:unallocated", -a)]
        else:  # saving: earmark bank money for a goal (negative = release back)
            goal = f"assets:goal:{t['goal_id']}" if t["goal_id"] else "assets:goal:deleted"
            lines += [(t["id"], goal, a), (t["id"], "assets:unallocated", -a)]
    for i in db.execute("SELECT * FROM investments WHERE user_id = ? AND status = 'holding'", (user_id,)):
        cost = i["quantity"] * i["price"]
        # The cost was released from the goal into bank (saving row −cost); it now sits in investments.
        lines += [(f"inv{i['id']}", "assets:investments", cost), (f"inv{i['id']}", "assets:unallocated", -cost)]
    return lines


def trial_balance(user_id):
    totals = {}
    for _ref, account, amount in journal(user_id):
        totals[account] = totals.get(account, 0) + amount
    return {"accounts": {k: rupees(v) for k, v in sorted(totals.items())},
            "sum": rupees(sum(totals.values())),
            "unallocated": rupees(totals.get("assets:unallocated", 0)),
            "available": rupees(available_balance(user_id))}


def align_to_bank(user_id):
    """Set the opening balance so Kitna's available balance equals the bank's latest reported balance.
    Money in goals and investments is still inside the bank account, so it's added back."""
    from .finance import invested_cost, opening_balance, total_saved

    bank = get_db().execute("SELECT balance FROM balance_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                            (user_id,)).fetchone()
    if bank is None:
        return None
    # bank account holds: available + goal cash (investments already left the bank)
    goal_cash = total_saved(user_id) - invested_cost(user_id)
    target_available = bank["balance"] - goal_cash
    diff = target_available - available_balance(user_id)
    new_opening = opening_balance(user_id) + diff
    get_db().execute("UPDATE users SET opening_balance = ? WHERE id = ?", (new_opening, user_id))
    return {"adjusted_by": rupees(diff), "opening_balance": rupees(new_opening)}


def bank_gap(user_id):
    """Bank balance minus what Kitna thinks is in the bank (available + goal cash), or None."""
    from .finance import invested_cost, total_saved

    bank = get_db().execute("SELECT balance FROM balance_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                            (user_id,)).fetchone()
    if bank is None:
        return None
    in_bank = available_balance(user_id) + total_saved(user_id) - invested_cost(user_id)
    return rupees(bank["balance"] - in_bank)
