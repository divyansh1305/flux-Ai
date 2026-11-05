"""Product analytics: what people do in Flux, counted so we can make it better.

Rules (also in the privacy page):
  * Events say WHAT happened ("plan_added", "screen_opened: home"), never amounts, merchants or message text.
  * Only totals are ever shown, on a page only the people in ADMIN_EMAILS can open.
  * Deleting an account deletes its events. Events older than 13 months are deleted; the daily totals stay.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from . import clock
from .db import get_db

log = logging.getLogger("flux.analytics")

# Every event name Flux records, and the values its `prop` may take ("" = no value). Anything else is refused,
# so a bug (or a crafted request) can never put personal data into this table.
EVENTS = {
    "signed_up": {"email", "google"},
    "setup_step": {"age", "money", "done"},
    "connected": {"gmail", "phone"},
    "auto_payment": {"sms", "notification", "email"},
    "message_unread": {"sms", "notification", "email"},
    "screen_opened": {"home", "activity", "plans", "ask", "goals", "budgets", "settings", "import", "share",
                      "privacy-center", "onboarding", "admin"},
    "plan_added": {"spend", "income"},
    "cushion_set": {""},
    "category_fixed": {""},
    "check_found": {"refund", "double", "price"},
    "check_dismissed": {"refund", "double", "price"},
    "refund_back": {""},
    "asked_flux": {"add_expense", "add_income", "check_balance", "spending_query", "budget_status", "logout", "set_budget", "goal_status",
                   "create_goal", "add_to_goal", "can_i_afford", "health_score", "forecast", "safe_to_spend", "bills",
                   "pay", "undo", "navigate", "help", "ask_coach", "unknown", "other"},
    "error_shown": {"home", "activity", "plans", "ask", "goals", "budgets", "settings", "import", "share",
                    "privacy-center", "onboarding", "admin", "other"},
}
CLIENT_EVENTS = {"screen_opened", "error_shown"}  # the only ones a browser may send


def track(user_id, name, prop=""):
    """Record one event. Never raises: analytics must not break the thing being measured."""
    try:
        allowed = EVENTS.get(name)
        if allowed is None:
            return False
        prop = str(prop or "")
        if prop not in allowed:
            prop = "other" if "other" in allowed else ""
            if prop not in allowed:
                return False
        get_db().execute("INSERT INTO events (user_id, name, prop) VALUES (?,?,?)", (user_id, name, prop))
        return True
    except Exception:  # pragma: no cover - defensive
        log.exception("could not record event %s", name)
        return False


# ─── nightly summary ─────────────────────────────────────────
def _utc_range(day):
    """Events are stored in UTC; a business day is an IST day."""
    start = datetime(day.year, day.month, day.day, tzinfo=clock.TZ).astimezone(timezone.utc).replace(tzinfo=None)
    end = start + timedelta(days=1)
    return start.isoformat(sep=" ", timespec="seconds"), end.isoformat(sep=" ", timespec="seconds")


def rollup(day=None):
    """Compute one day's totals into daily_stats (safe to run again: it overwrites that day)."""
    day = day or (clock.today() - timedelta(days=1))
    db = get_db()
    a, b = _utc_range(day)
    one = lambda sql, *args: db.execute(sql, args).fetchone()[0] or 0  # noqa: E731
    stats = {
        "signups": one("SELECT COUNT(*) FROM events WHERE name='signed_up' AND created_at >= ? AND created_at < ?", a, b),
        "setup_done": one("SELECT COUNT(*) FROM events WHERE name='setup_step' AND prop='done' AND created_at >= ? AND created_at < ?", a, b),
        "active_users": one("SELECT COUNT(DISTINCT user_id) FROM events WHERE name='screen_opened' AND created_at >= ? AND created_at < ?", a, b),
        "plans_added": one("SELECT COUNT(*) FROM events WHERE name='plan_added' AND created_at >= ? AND created_at < ?", a, b),
        "asked_flux": one("SELECT COUNT(*) FROM events WHERE name='asked_flux' AND created_at >= ? AND created_at < ?", a, b),
        "errors": one("SELECT COUNT(*) FROM events WHERE name='error_shown' AND created_at >= ? AND created_at < ?", a, b),
        "refunds_back": one("SELECT COUNT(*) FROM events WHERE name='refund_back' AND created_at >= ? AND created_at < ?", a, b),
    }
    for src in ("sms", "notification", "email"):
        stats[f"auto_payments_{src}"] = one("SELECT COUNT(*) FROM events WHERE name='auto_payment' AND prop=? AND created_at >= ? AND created_at < ?", src, a, b)
        stats[f"unread_{src}"] = one("SELECT COUNT(*) FROM events WHERE name='message_unread' AND prop=? AND created_at >= ? AND created_at < ?", src, a, b)
    for t in ("refund", "double", "price"):
        stats[f"checks_found_{t}"] = one("SELECT COUNT(*) FROM events WHERE name='check_found' AND prop=? AND created_at >= ? AND created_at < ?", t, a, b)
        stats[f"checks_dismissed_{t}"] = one("SELECT COUNT(*) FROM events WHERE name='check_dismissed' AND prop=? AND created_at >= ? AND created_at < ?", t, a, b)
    stats["users_total"] = one("SELECT COUNT(*) FROM users WHERE created_at < ?", b)
    db.executemany("INSERT INTO daily_stats (day, metric, value) VALUES (?,?,?) ON CONFLICT(day, metric) DO UPDATE SET value = excluded.value",
                   [(day.isoformat(), k, float(v)) for k, v in stats.items()])
    db.commit()
    return stats


def purge_old(days=400):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
    n = get_db().execute("DELETE FROM events WHERE created_at < ?", (cutoff,)).rowcount
    get_db().commit()
    return n


def nightly():
    """For the daily scheduled task: yesterday's totals (and fill any missed day in the last week)."""
    today = clock.today()
    have = {r["day"] for r in get_db().execute("SELECT DISTINCT day FROM daily_stats WHERE day >= ?",
                                               ((today - timedelta(days=8)).isoformat(),))}
    done = []
    for back in range(7, 0, -1):
        d = today - timedelta(days=back)
        if d.isoformat() not in have or back == 1:
            rollup(d)
            done.append(d.isoformat())
    return {"rolled_up": done, "purged_events": purge_old()}


# ─── numbers page ────────────────────────────────────────────
def _pct(n, d):
    return round(100 * n / d) if d else None


def overview():
    """Everything the private numbers page shows. Totals only."""
    db = get_db()
    q = lambda sql, *args: db.execute(sql, args).fetchone()[0] or 0  # noqa: E731
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    since = lambda days: (now - timedelta(days=days)).isoformat(sep=" ", timespec="seconds")  # noqa: E731

    totals = {
        "users": q("SELECT COUNT(*) FROM users"),
        "setup_done": q("SELECT COUNT(*) FROM users WHERE onboarded = 1"),
        "connected": q("SELECT COUNT(*) FROM users u WHERE EXISTS (SELECT 1 FROM gmail_accounts g WHERE g.user_id=u.id)"
                       " OR EXISTS (SELECT 1 FROM ingest_tokens t WHERE t.user_id=u.id)"),
        "with_auto_payment": q("SELECT COUNT(DISTINCT user_id) FROM transactions WHERE source IN ('sms','notification','email')"),
        "active_7d": q("SELECT COUNT(DISTINCT user_id) FROM events WHERE name='screen_opened' AND created_at >= ?", since(7)),
        "active_30d": q("SELECT COUNT(DISTINCT user_id) FROM events WHERE name='screen_opened' AND created_at >= ?", since(30)),
        "payments_auto_30d": q("SELECT COUNT(*) FROM events WHERE name='auto_payment' AND created_at >= ?", since(30)),
        "refunds_back": q("SELECT COUNT(*) FROM refund_watch WHERE status='back'"),
        "kept_rupees": q("SELECT COALESCE(SUM(amount),0) FROM refund_watch WHERE status='back'") / 100,
    }

    # Setup funnel for people who signed up in the last 30 days.
    cohort = "SELECT user_id FROM events WHERE name='signed_up' AND created_at >= ?"
    s30 = since(30)
    signed = q(f"SELECT COUNT(*) FROM ({cohort})", s30)
    step = lambda prop: q(f"SELECT COUNT(DISTINCT user_id) FROM events WHERE name='setup_step' AND prop=? AND user_id IN ({cohort})", prop, s30)  # noqa: E731
    conn = q(f"SELECT COUNT(DISTINCT user_id) FROM events WHERE name='connected' AND user_id IN ({cohort})", s30)
    first = q(f"SELECT COUNT(DISTINCT user_id) FROM events WHERE name='auto_payment' AND user_id IN ({cohort})", s30)
    funnel = [{"step": label, "users": n, "pct": _pct(n, signed)} for label, n in (
        ("Signed up", signed), ("Confirmed 18+", step("age")), ("Answered money question", step("money")),
        ("Finished setup", step("done")), ("Connected payments", conn), ("Got a payment automatically", first))]

    # Retention: of people who signed up 8-60 days ago, how many came back on day 1, in days 7-13, in days 30-36.
    rows = db.execute("SELECT user_id, created_at FROM events WHERE name='signed_up' AND created_at < ? AND created_at >= ?",
                      (since(8), since(60))).fetchall()

    def came_back(uid, start, a, b):
        lo = (start + timedelta(days=a)).isoformat(sep=" ", timespec="seconds")
        hi = (start + timedelta(days=b)).isoformat(sep=" ", timespec="seconds")
        return db.execute("SELECT 1 FROM events WHERE user_id=? AND name='screen_opened' AND created_at >= ? AND created_at < ? LIMIT 1",
                          (uid, lo, hi)).fetchone() is not None

    ret = {"cohort": len(rows), "day1": 0, "day7": 0, "day30": 0, "day30_cohort": 0}
    for r in rows:
        start = datetime.fromisoformat(r["created_at"])
        ret["day1"] += came_back(r["user_id"], start, 1, 2)
        ret["day7"] += came_back(r["user_id"], start, 7, 14)
        if start <= now - timedelta(days=37):
            ret["day30_cohort"] += 1
            ret["day30"] += came_back(r["user_id"], start, 30, 37)
    retention = {"cohort": ret["cohort"], "day1": _pct(ret["day1"], ret["cohort"]), "day7": _pct(ret["day7"], ret["cohort"]),
                 "day30": _pct(ret["day30"], ret["day30_cohort"]), "day30_cohort": ret["day30_cohort"]}

    group = lambda name, days: [dict(r) for r in db.execute(  # noqa: E731
        "SELECT prop AS name, COUNT(*) AS count, COUNT(DISTINCT user_id) AS users FROM events WHERE name=? AND created_at >= ?"
        " GROUP BY prop ORDER BY count DESC", (name, since(days)))]
    sources = {r["name"]: {"logged": r["count"]} for r in group("auto_payment", 30)}
    for r in group("message_unread", 30):
        sources.setdefault(r["name"], {"logged": 0})["unread"] = r["count"]
    for v in sources.values():
        v.setdefault("unread", 0)
        v["read_rate"] = _pct(v["logged"], v["logged"] + v["unread"])
    found = {r["name"]: r["count"] for r in group("check_found", 90)}
    dismissed = {r["name"]: r["count"] for r in group("check_dismissed", 90)}
    checks = [{"type": t, "found": found.get(t, 0), "dismissed": dismissed.get(t, 0)} for t in ("refund", "double", "price")]

    today = clock.today()
    series = {}
    for r in db.execute("SELECT day, metric, value FROM daily_stats WHERE day >= ? AND metric IN ('signups','active_users')",
                        ((today - timedelta(days=30)).isoformat(),)):
        series.setdefault(r["day"], {})[r["metric"]] = r["value"]
    daily = [{"day": (today - timedelta(days=i)).isoformat(),
              **{"signups": 0, "active_users": 0, **series.get((today - timedelta(days=i)).isoformat(), {})}}
             for i in range(30, 0, -1)]
    return {"totals": totals, "funnel": funnel, "retention": retention, "sources": sources, "checks": checks,
            "screens": group("screen_opened", 30), "questions": group("asked_flux", 30)[:10],
            "errors": group("error_shown", 7), "daily": daily, "generated_at": now.isoformat(timespec="seconds") + "Z"}
