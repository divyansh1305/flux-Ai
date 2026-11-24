"""Kitna Rent Pro payments (Razorpay). See flux/billing.py."""
from flask import Blueprint, jsonify, request

from .. import analytics, billing, rent
from ..security import ApiError, current_user, json_body, login_required, rate_limit

bp = Blueprint("billing", __name__, url_prefix="/api/billing")


@bp.get("")
@login_required
def status():
    u = current_user()
    return jsonify({"enabled": billing.enabled(), "plans": billing.plans_json(), **rent.plan_json(u),
                    "history": billing.history(u["id"])})


@bp.post("/order")
@login_required
@rate_limit(10, 600, scope="billing_order")
def order():
    data = json_body()
    analytics.track(current_user()["id"], "upgrade_opened", data.get("from") if data.get("from") in ("limit", "menu", "banner") else "menu")
    return jsonify(billing.create_order(current_user(), data.get("plan")))


@bp.post("/verify")
@login_required
@rate_limit(20, 600, scope="billing_verify")
def verify():
    d = json_body()
    for k in ("razorpay_order_id", "razorpay_payment_id", "razorpay_signature"):
        if not isinstance(d.get(k), str) or not d[k] or len(d[k]) > 200:
            raise ApiError("Payment details are missing.")
    until = billing.verify(current_user(), d["razorpay_order_id"], d["razorpay_payment_id"], d["razorpay_signature"])
    return jsonify({"ok": True, "until": until})


@bp.post("/webhook")
@rate_limit(120, 60, scope="billing_webhook")
def webhook():
    raw = request.get_data(cache=True)
    ok = billing.webhook(raw, request.headers.get("X-Razorpay-Signature", ""), request.get_json(silent=True))
    return jsonify({"ok": True, "handled": ok})
