"""The Sunday note: last week in a few lines, worked out from the user's own payments (no AI, no guessing).

    "You spent ₹3,200 this week, ₹800 less than usual. Food & Dining was the biggest part (₹1,400).
     Coming up: Netflix ₹649 on 12 Nov. Friends owe you ₹1,500."
"""
from datetime import timedelta

from . import clock
from .db import get_db
from .finance import own_sum, rupees


def _inr(paise):
    return f"₹{rupees(paise):,.0f}"


def _d(iso):
    from datetime import date

    return date.fromisoformat(iso).strftime("%-d %b")


def note(user, today=None):
    """The 7 days before `today`, compared with the 4 weeks before that."""
    from . import friends, insights

    hi = (user["lang"] if "lang" in user.keys() else "en") == "hinglish"
    uid = user["id"]
    today = today or clock.today()
    start, end = today - timedelta(days=7), today - timedelta(days=1)
    spent = own_sum(uid, "expense", start, end)
    db = get_db()
    weeks = []
    for i in range(1, 5):
        s, e = start - timedelta(days=7 * i), end - timedelta(days=7 * i)
        if db.execute("SELECT 1 FROM transactions WHERE user_id = ? AND kind IN ('expense','income') AND date BETWEEN ? AND ? LIMIT 1",
                      (uid, s.isoformat(), e.isoformat())).fetchone():
            weeks.append(own_sum(uid, "expense", s, e))
    usual = round(sum(weeks) / len(weeks)) if len(weeks) >= 2 else None

    cat = db.execute(
        "SELECT t.category, SUM(t.amount - COALESCE((SELECT SUM(o.amount) FROM owed o WHERE o.transaction_id = t.id"
        " AND o.direction='they_owe'),0)) AS total FROM transactions t WHERE t.user_id = ? AND t.kind = 'expense'"
        " AND t.date BETWEEN ? AND ? GROUP BY t.category ORDER BY total DESC LIMIT 1",
        (uid, start.isoformat(), end.isoformat())).fetchone()
    count = db.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ? AND kind = 'expense' AND date BETWEEN ? AND ?",
                       (uid, start.isoformat(), end.isoformat())).fetchone()[0]
    big = db.execute("SELECT note, category, amount, date FROM transactions WHERE user_id = ? AND kind = 'expense'"
                     " AND date BETWEEN ? AND ? ORDER BY amount DESC LIMIT 1",
                     (uid, start.isoformat(), end.isoformat())).fetchone()

    if not spent:
        headline = "Is hafte koi kharcha nahi dikha." if hi else "No spending this week."
    elif usual is None:
        headline = f"Is hafte {_inr(spent)} kharch hue." if hi else f"You spent {_inr(spent)} this week."
    else:
        diff = spent - usual
        if abs(diff) <= 0.1 * usual:
            headline = (f"Is hafte {_inr(spent)} kharch hue, roz jitna hi." if hi
                        else f"You spent {_inr(spent)} this week, about the same as usual.")
        elif diff < 0:
            headline = (f"Is hafte {_inr(spent)} kharch hue, aam se {_inr(-diff)} kam. Badhiya!" if hi
                        else f"You spent {_inr(spent)} this week, {_inr(-diff)} less than usual. Nice.")
        else:
            headline = (f"Is hafte {_inr(spent)} kharch hue, aam se {_inr(diff)} zyada." if hi
                        else f"You spent {_inr(spent)} this week, {_inr(diff)} more than usual.")

    lines = []
    if cat and cat["total"] and spent:
        lines.append((f"Sabse zyada: {cat['category']} ({_inr(cat['total'])})" if hi
                      else f"Biggest part: {cat['category']} ({_inr(cat['total'])})"))
    if big and count >= 2:
        lines.append((f"Sabse bada payment: {big['note'] or big['category']} {_inr(big['amount'])} ({_d(big['date'])})" if hi
                      else f"Largest payment: {big['note'] or big['category']} {_inr(big['amount'])} on {_d(big['date'])}"))
    week_end = (today + timedelta(days=7)).isoformat()
    bills = [b for b in insights.recurring(uid) if today.isoformat() <= b["next_date"] < week_end]
    plans = db.execute("SELECT title, amount, date FROM plans WHERE user_id = ? AND done = 0 AND kind = 'spend'"
                       " AND date >= ? AND date < ? ORDER BY date", (uid, today.isoformat(), week_end)).fetchall()
    coming = [f"{b['name']} ₹{b['amount']:,.0f} ({_d(b['next_date'])})" for b in bills[:3]]
    coming += [f"{p['title']} {_inr(p['amount'])} ({_d(p['date'])})" for p in plans[:3]]
    if coming:
        lines.append(("Aane wala: " if hi else "Coming up: ") + ", ".join(coming[:4]))
    owe = friends.totals(uid)
    if owe["they_owe"]:
        lines.append((f"Doston se lene hain: ₹{owe['they_owe']:,.0f}" if hi else f"Friends owe you ₹{owe['they_owe']:,.0f}"))
    if owe["i_owe"]:
        lines.append((f"Doston ko dene hain: ₹{owe['i_owe']:,.0f}" if hi else f"You owe friends ₹{owe['i_owe']:,.0f}"))
    refunds = db.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM refund_watch WHERE user_id = ? AND status='open'",
                         (uid,)).fetchone()
    if refunds[0]:
        lines.append((f"Refund aana baaki: {_inr(refunds[1])}" if hi else f"Refunds still to come back: {_inr(refunds[1])}"))
    return {"start": start.isoformat(), "end": end.isoformat(), "spent": rupees(spent),
            "usual": rupees(usual) if usual is not None else None, "headline": headline, "lines": lines,
            "has_data": bool(spent) or bool(lines)}
