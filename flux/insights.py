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


def safe_to_spend(user_id, user=None):
    """How much can be spent today without breaking upcoming bills or this month's goal plan.

    safe_daily = (available balance − bills due before month end − goal top-ups still planned this month)
                 ÷ days left in the month (including today)
    left_today = safe_daily − already spent today
    """
    today = clock.today()
    first, last = month_bounds(today)
    days_left = (last - today).days + 1
    avail = balance(user_id)
    db = get_db()

    bills = [b for b in recurring(user_id) if today.isoformat() <= b["next_date"] <= last.isoformat()]
    bills_due = sum(round(b["amount"] * 100) for b in bills)

    goal_reserve = 0
    for g in db.execute(
            "SELECT g.id, g.title, g.target, g.deadline, COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.goal_id=g.id"
            " AND t.kind='saving'),0) + COALESCE((SELECT SUM(quantity*price) FROM investments i WHERE i.goal_id=g.id"
            " AND i.status='holding'),0) AS saved FROM goals g WHERE g.user_id = ? AND g.archived = 0 AND g.deadline IS NOT NULL",
            (user_id,)):
        remaining = g["target"] - g["saved"]
        if remaining <= 0:
            continue
        deadline = date.fromisoformat(g["deadline"])
        months = max(1, (deadline.year - today.year) * 12 + deadline.month - today.month + (1 if deadline.day >= today.day else 0))
        monthly = remaining / months
        saved_this_month = db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE goal_id = ? AND kind='saving' AND date >= ?",
            (g["id"], first.isoformat())).fetchone()[0]
        goal_reserve += max(0, round(monthly - saved_this_month))

    spent_today = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id = ? AND kind='expense' AND date = ?",
        (user_id, today.isoformat())).fetchone()[0]
    pool = avail + spent_today - bills_due - goal_reserve  # today's spend is part of today's allowance
    daily = max(0, pool) / days_left
    left_today = max(0, daily - spent_today)
    over_budget = [b["category"] for b in budget_status(user_id, today) if b["state"] == "over"]
    if pool <= 0:
        status, message = "stop", "Upcoming bills and goal savings need everything you have. Avoid non-essential spends."
    elif left_today <= 0:
        status, message = "used", "You've used today's safe amount. Tomorrow's resets."
    else:
        status, message = "ok", f"Spend up to ₹{rupees(round(left_today)):,.0f} more today and stay on track."
    if over_budget:
        message += " Over budget: " + ", ".join(over_budget) + "."
    return {"left_today": rupees(round(left_today)), "daily": rupees(round(daily)), "spent_today": rupees(spent_today),
            "available": rupees(avail), "bills_due": rupees(bills_due), "bills": bills, "goal_reserve": rupees(goal_reserve),
            "days_left": days_left, "status": status, "message": message,
            "method": "(available − bills due this month − planned goal savings) ÷ days left, minus what you've spent today."}


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
        if autosaved:
            verdict += f" Auto-save put away ₹{rupees(autosaved):,.0f}, {autosaved / cb_total:.1f}× the cashback, with no extra spending."
        if rate < 1:
            verdict += " Cashback is worth less than 1% of what you spend: don't let it decide what you buy."
    return {"days": days, "cashback": rupees(cb_total), "cashback_count": cb_count, "spend": rupees(spend),
            "cashback_rate": round(rate, 2), "autosaved": rupees(autosaved), "verdict": verdict}
