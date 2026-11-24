"""Kitna Rent Pro, paid through Razorpay.

Flow (Razorpay Standard Checkout):
  1. /api/billing/order    server creates a Razorpay order for a fixed plan price (the browser never sets the price)
  2. the browser opens Razorpay Checkout; the user pays by UPI, card or net banking on Razorpay's own screen
  3. /api/billing/verify   the browser hands back order id, payment id and signature; the server checks the
                           HMAC-SHA256 signature with the key secret before giving the plan
  4. /api/billing/webhook  Razorpay also calls the server directly (order.paid), so a closed tab never loses a payment
Every step is idempotent: an order can only ever extend the plan once.
"""
import hashlib
import hmac
from datetime import date

import requests
from flask import current_app

from . import clock
from .db import get_db
from .security import ApiError

API = "https://api.razorpay.com/v1"
PLANS = {
    "rent_month": {"name": "Kitna Rent Pro · 1 month", "amount": 299_00, "months": 1},
    "rent_year": {"name": "Kitna Rent Pro · 12 months", "amount": 2_999_00, "months": 12},
}


def enabled():
    cfg = current_app.config
    return bool(cfg.get("RAZORPAY_KEY_ID") and cfg.get("RAZORPAY_KEY_SECRET"))


def plans_json():
    return [{"id": k, "name": v["name"], "price": v["amount"] / 100, "months": v["months"]} for k, v in PLANS.items()]


def create_order(user, plan_id):
    if plan_id not in PLANS:
        raise ApiError("Pick a plan.")
    if not enabled():
        raise ApiError("Payments aren't switched on yet.", 503)
    plan = PLANS[plan_id]
    cfg = current_app.config
    try:
        r = requests.post(f"{API}/orders", auth=(cfg["RAZORPAY_KEY_ID"], cfg["RAZORPAY_KEY_SECRET"]), timeout=15,
                          json={"amount": plan["amount"], "currency": "INR", "receipt": f"u{user['id']}-{plan_id}",
                                "notes": {"user_id": str(user["id"]), "plan": plan_id}})
    except requests.RequestException:
        raise ApiError("Couldn't reach Razorpay. Please try again.", 502)
    if r.status_code != 200:
        current_app.logger.warning("Razorpay order refused: %s %s", r.status_code, r.text[:200])
        raise ApiError("Couldn't start the payment. Please try again.", 502)
    order = r.json()
    get_db().execute("INSERT INTO billing_orders (user_id, order_id, plan, amount, months) VALUES (?,?,?,?,?)",
                     (user["id"], order["id"], plan_id, plan["amount"], plan["months"]))
    get_db().commit()
    return {"key": cfg["RAZORPAY_KEY_ID"], "order_id": order["id"], "amount": plan["amount"], "currency": "INR",
            "name": "Kitna", "description": plan["name"], "email": user["email"], "user_name": user["name"]}


def _sig_ok(message, signature, secret):
    if not (secret and signature and isinstance(signature, str)):
        return False
    digest = hmac.new(secret.encode(), message if isinstance(message, bytes) else message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def add_months(d, months):
    y, m = d.year, d.month + months
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    from calendar import monthrange

    return date(y, m, min(d.day, monthrange(y, m)[1]))


def _mark_paid(order_id, payment_id):
    """Give the plan for this order, once. Returns the new end date, or None if already given / unknown."""
    db = get_db()
    o = db.execute("SELECT * FROM billing_orders WHERE order_id = ?", (order_id,)).fetchone()
    if o is None or o["status"] == "paid":
        return None
    u = db.execute("SELECT plan_until FROM users WHERE id = ?", (o["user_id"],)).fetchone()
    today = clock.today()
    start = max(today, date.fromisoformat(u["plan_until"])) if u and u["plan_until"] else today
    until = add_months(start, o["months"]).isoformat()
    cur = db.execute("UPDATE billing_orders SET status = 'paid', payment_id = ?, paid_at = datetime('now')"
                     " WHERE order_id = ? AND status != 'paid'", (payment_id, order_id))
    if cur.rowcount == 0:
        return None
    db.execute("UPDATE users SET plan_until = ? WHERE id = ?", (until, o["user_id"]))
    db.commit()
    from .analytics import track

    track(o["user_id"], "plan_bought", o["plan"])
    return until


def verify(user, order_id, payment_id, signature):
    o = get_db().execute("SELECT * FROM billing_orders WHERE order_id = ? AND user_id = ?", (order_id, user["id"])).fetchone()
    if o is None:
        raise ApiError("Payment not found.", 404)
    if not _sig_ok(f"{order_id}|{payment_id}", signature, current_app.config.get("RAZORPAY_KEY_SECRET")):
        raise ApiError("We couldn't confirm this payment. If money left your account, it will show up within a few minutes.", 400)
    _mark_paid(order_id, payment_id)
    return get_db().execute("SELECT plan_until FROM users WHERE id = ?", (user["id"],)).fetchone()["plan_until"]


def webhook(raw_body, signature, payload):
    if not _sig_ok(raw_body, signature, current_app.config.get("RAZORPAY_WEBHOOK_SECRET")):
        raise ApiError("Bad signature.", 400)
    event = (payload or {}).get("event", "")
    p = ((payload or {}).get("payload") or {})
    if event == "order.paid":
        order_id = ((p.get("order") or {}).get("entity") or {}).get("id")
        payment_id = ((p.get("payment") or {}).get("entity") or {}).get("id")
    elif event == "payment.captured":
        ent = (p.get("payment") or {}).get("entity") or {}
        order_id, payment_id = ent.get("order_id"), ent.get("id")
    else:
        return False
    if order_id and payment_id:
        _mark_paid(order_id, payment_id)
        return True
    return False


def history(user_id):
    return [{"plan": r["plan"], "amount": r["amount"] / 100, "paid_at": r["paid_at"], "payment_id": r["payment_id"]}
            for r in get_db().execute("SELECT * FROM billing_orders WHERE user_id = ? AND status = 'paid' ORDER BY id DESC",
                                      (user_id,))]
