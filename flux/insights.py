"""Forward-looking insights: recurring bills, safe-to-spend today, cashback vs auto-save."""
import re
import statistics
from datetime import date, timedelta

from . import clock
from .db import get_db
from .finance import balance, budget_status, month_bounds, rupees


def _key(note, category):
    base = re.sub(r"[^a-z]+", " ", (note or "").lower()).strip()
    base = re.sub(r"\b(upi|payment|paid|to|bill|recharge|autopay|subscription)\b", " ", base)
    base = " ".join(base.split()[:3])
    return base or category.lower()


def recurring(user_id, lookback_days=150):
    """Detect bills and subscriptions: same payee, similar amount, regular gap (weekly or monthly)."""
    today = clock.today()
    rows = get_db().execute(
        "SELECT note, category, amount, date FROM transactions WHERE user_id = ? AND kind = 'expense'"
        " AND date >= ? AND category NOT IN ('Transfers') ORDER BY date",
        (user_id, (today - timedelta(days=lookback_days)).isoformat())).fetchall()
    groups = {}
    for r in rows:
        groups.setdefault(_key(r["note"], r["category"]), []).append(r)
    out = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        dates = sorted({date.fromisoformat(i["date"]) for i in items})
        if len(dates) < 2:
            continue
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        gap = statistics.median(gaps)
        if 26 <= gap <= 35:
            cadence, step = "monthly", 30
        elif 6 <= gap <= 8:
            cadence, step = "weekly", 7
        else:
            continue
        if max(gaps) - min(gaps) > (6 if cadence == "monthly" else 2):
            continue
        amounts = [i["amount"] for i in items]
        med = statistics.median(amounts)
        if any(abs(a - med) > 0.2 * med for a in amounts[-3:]):  # amounts must be stable-ish
            continue
        last = dates[-1]
        nxt = last + timedelta(days=round(gap))
        while nxt < today - timedelta(days=3):  # missed / not yet logged cycles
            nxt += timedelta(days=step)
        out.append({"name": items[-1]["note"] or items[-1]["category"], "category": items[-1]["category"],
                    "amount": rupees(round(med)), "cadence": cadence, "last_date": last.isoformat(),
                    "next_date": nxt.isoformat(), "times_seen": len(items),
                    "monthly_cost": rupees(round(med * (30 / step)))})
    out.sort(key=lambda x: x["next_date"])
    return out


def next_income_date(user, today):
    """The day the user's next money is expected (exclusive end of the current cycle).
    Monthly income on a set date -> next occurrence of that date. Otherwise -> the 1st of next month."""
    import calendar

    pattern = user["income_pattern"] if user is not None else "unset"
    pay_day = user["pay_day"] if user is not None else None
    if pattern == "monthly" and pay_day:
        def on(y, m):
            return date(y, m, min(pay_day, calendar.monthrange(y, m)[1]))
        cand = on(today.year, today.month)
        if cand <= today:
            y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
            cand = on(y, m)
        return cand, "payday"
    _, last = month_bounds(today)
    return last + timedelta(days=1), "month_end"


def _plans_in_window(user_id, start, end):
    return get_db().execute(
        "SELECT * FROM plans WHERE user_id = ? AND done = 0 AND date >= ? AND date < ? ORDER BY date",
        (user_id, start.isoformat(), end.isoformat())).fetchall()


def safe_to_spend(user_id, user=None):
    """How much can be spent today without breaking what's coming before the next money arrives.

    pool  = money you have
          + money you're sure is coming before then (income plans marked sure)
          - bills and subscriptions due before then (spotted from history)
          - your plans before then ("Dinner Friday ₹2,000")
          - goal top-ups planned for this month
          - your safety cushion (never counted as spendable)
    daily = pool ÷ days until the next money; left today = daily − already spent today.
    Unspent money stays in the pool, so tomorrow's number goes up rather than being "used or lost".
    """
    from . import ledger

    db = get_db()
    if user is None:
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    today = clock.today()
    first, _ = month_bounds(today)
    end, horizon = next_income_date(user, today)
    days_left = max(1, (end - today).days)
    avail = balance(user_id)

    bills = [b for b in recurring(user_id) if today.isoformat() <= b["next_date"] < end.isoformat()]
    bills_due = sum(round(b["amount"] * 100) for b in bills)

    spent_today_rows = db.execute(
        "SELECT amount FROM transactions WHERE user_id = ? AND kind='expense' AND date = ?", (user_id, today.isoformat())).fetchall()
    spent_today = sum(r["amount"] for r in spent_today_rows)

    plans_spend, plans_in, maybe_in, plan_items = 0, 0, 0, []
    used = set()
    for p in _plans_in_window(user_id, today, end):
        if p["kind"] == "spend":
            # A plan for today that matches a payment made today (±20%) has happened: don't count it twice.
            if p["date"] == today.isoformat():
                match = next((i for i, r in enumerate(spent_today_rows) if i not in used
                              and abs(r["amount"] - p["amount"]) <= 0.2 * p["amount"]), None)
                if match is not None:
                    used.add(match)
                    continue
            plans_spend += p["amount"]
        elif p["sure"]:
            plans_in += p["amount"]
        else:
            maybe_in += p["amount"]
        plan_items.append({"id": p["id"], "title": p["title"], "amount": rupees(p["amount"]), "date": p["date"],
                           "kind": p["kind"], "sure": bool(p["sure"])})

    goal_reserve = 0
    for g in db.execute(
            "SELECT g.id, g.target, g.deadline, COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.goal_id=g.id"
            " AND t.kind='saving'),0) AS saved FROM goals g WHERE g.user_id = ? AND g.archived = 0 AND g.deadline IS NOT NULL",
            (user_id,)):
        remaining = g["target"] - g["saved"]
        if remaining <= 0:
            continue
        deadline = date.fromisoformat(g["deadline"])
        months = max(1, (deadline.year - today.year) * 12 + deadline.month - today.month + (1 if deadline.day >= today.day else 0))
        saved_this_month = db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE goal_id = ? AND kind='saving' AND date >= ?",
            (g["id"], first.isoformat())).fetchone()[0]
        goal_reserve += max(0, round(remaining / months - saved_this_month))

    # Money paid for a plan today was already planned: it isn't part of today's everyday allowance.
    everyday_today = spent_today - sum(spent_today_rows[i]["amount"] for i in used)
    cushion = user["cushion"] if user is not None else 0
    pool = avail + everyday_today + plans_in - bills_due - plans_spend - goal_reserve - cushion
    daily = max(0, pool) / days_left
    left_today = max(0, daily - everyday_today)
    maybe_daily = maybe_in / days_left if maybe_in else 0

    confirmed = ledger.latest_bank_balance(user_id) is not None
    has_money = avail > 0 or plans_in > 0
    over_budget = [b["category"] for b in budget_status(user_id, today) if b["state"] == "over"]
    if not has_money:
        status, message = "setup", "Add your money in (salary, pocket money) or confirm your bank balance, and Flux works out today's number."
    elif pool <= 0:
        status, message = "stop", "Bills, plans and your cushion need everything you have until your next money. Only spend on essentials."
    elif left_today <= 0:
        status, message = "used", "You've spent today's safe amount. Whatever you don't spend tomorrow carries forward."
    else:
        status, message = "ok", f"Spend up to ₹{rupees(round(left_today)):,.0f} more today and you're fine until {end.strftime('%-d %b')}."
    if over_budget:
        message += " Over budget: " + ", ".join(over_budget) + "."

    lines = [{"label": "Money you have" + ("" if confirmed else " (not yet matched with your bank)"), "amount": rupees(avail + everyday_today)}]
    if plans_in:
        lines.append({"label": "Sure money coming before then", "amount": rupees(plans_in)})
    if bills_due:
        lines.append({"label": f"Bills due ({len(bills)})", "amount": -rupees(bills_due)})
    if plans_spend:
        lines.append({"label": "Your plans", "amount": -rupees(plans_spend)})
    if goal_reserve:
        lines.append({"label": "Goal top-ups this month", "amount": -rupees(goal_reserve)})
    if cushion:
        lines.append({"label": "Safety cushion (kept aside)", "amount": -rupees(cushion)})
    until = "your next payday" if horizon == "payday" else "the end of the month"
    return {"left_today": rupees(round(left_today)), "daily": rupees(round(daily)), "spent_today": rupees(spent_today),
            "available": rupees(avail), "bills_due": rupees(bills_due), "bills": bills, "goal_reserve": rupees(goal_reserve),
            "plans_reserved": rupees(plans_spend), "sure_income": rupees(plans_in), "plans": plan_items,
            "cushion": rupees(cushion), "maybe_extra_daily": rupees(round(maybe_daily)),
            "pool": rupees(max(0, pool)), "days_left": days_left, "until": end.isoformat(), "until_label": until,
            "horizon": horizon, "confirmed": confirmed, "status": status, "message": message, "lines": lines,
            "method": f"(money you have + sure money coming − bills − plans − goal top-ups − cushion) ÷ {days_left} "
                      f"day{'s' if days_left != 1 else ''} until {until}, minus what you've spent today."}


def cashback_report(user_id, days=90):
    """The 'cashback trap' measured: cashback received vs spending, vs what auto-save put away."""
    since = (clock.today() - timedelta(days=days - 1)).isoformat()
    db = get_db()
    cashback = db.execute("SELECT COALESCE(SUM(amount),0), COUNT(*) FROM transactions WHERE user_id=? AND kind='income'"
                          " AND category='Cashback' AND date >= ?", (user_id, since)).fetchone()
    spend = db.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND kind='expense'"
                       " AND category NOT IN ('Transfers','Investments','Rent') AND date >= ?", (user_id, since)).fetchone()[0]
    autosaved = db.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND kind='saving'"
                           " AND source='autosave' AND date >= ?", (user_id, since)).fetchone()[0]
    cb_total, cb_count = cashback[0], cashback[1]
    rate = cb_total / spend * 100 if spend else 0
    if cb_count == 0:
        verdict = "No cashback seen yet. When cashback credits arrive by SMS, Flux compares them with your spending."
    else:
        verdict = (f"You received ₹{rupees(cb_total):,.0f} cashback on ₹{rupees(spend):,.0f} of everyday spending "
                   f"({rate:.2f}% back).")
        if rate < 1:
            verdict += " Cashback is worth less than 1% of what you spend: don't let it decide what you buy."
    return {"days": days, "cashback": rupees(cb_total), "cashback_count": cb_count, "spend": rupees(spend),
            "cashback_rate": round(rate, 2), "autosaved": rupees(autosaved), "verdict": verdict}
