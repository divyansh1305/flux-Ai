"""Kitna Rent API (owner side) and the tenant's own page (/r/<token>)."""
import re

from flask import Blueprint, jsonify, request

from .. import analytics, clock, rent
from ..db import get_db
from ..security import ApiError, clean_text, current_user, json_body, login_required, parse_amount, parse_date, rate_limit

bp = Blueprint("rent", __name__)

VPA_RE = re.compile(r"^[A-Za-z0-9.\-_]{2,256}@[A-Za-z][A-Za-z0-9.\-]{1,63}$")


def _base():
    return request.host_url.rstrip("/")


def _tenant_payload(data, partial=False):
    out = {}
    if not partial or "name" in data:
        out["name"] = clean_text(data.get("name"), "Name", 60, required=True)
    if not partial or "rent" in data:
        out["rent"] = parse_amount(data.get("rent"), "Rent")
        if out["rent"] > 10_00_000_00:
            raise ApiError("That rent looks too high. Check the amount.")
    for k, label, n in (("phone", "Phone", 20), ("room", "Room", 20), ("payer_names", "Who else pays", 120)):
        if not partial or k in data:
            out[k] = clean_text(data.get(k), label, n)
    if out.get("phone") and len(re.sub(r"\D", "", out["phone"])) not in (10, 12):
        raise ApiError("Enter a 10-digit mobile number.")
    if not partial or "start_month" in data:
        out["start_month"] = rent.valid_month(data.get("start_month") or rent.month_of(clock.today()), "First month")
    if not partial or "opening_due" in data:
        out["opening_due"] = parse_amount(data.get("opening_due") or 0, "Old dues", allow_zero=True)
    return out


@bp.get("/api/rent")
@login_required
def overview():
    return jsonify(rent.overview(current_user(), _base()))


@bp.put("/api/rent/property")
@login_required
def save_property():
    data = json_body()
    name = clean_text(data.get("name"), "PG or flat name", 60, required=True)
    upi = clean_text(data.get("upi_id"), "UPI ID", 100).lower()
    if upi and not VPA_RE.match(upi):
        raise ApiError("Enter a UPI ID like yourname@okaxis.")
    try:
        due_day = int(data.get("due_day") or 5)
    except (TypeError, ValueError):
        raise ApiError("Rent due day must be a number.")
    if not 1 <= due_day <= 28:
        raise ApiError("Rent due day must be between 1 and 28.")
    new = rent.get_property(current_user()["id"]) is None
    p = rent.save_property(current_user()["id"], name, upi, due_day)
    if new:
        analytics.track(current_user()["id"], "rent_setup", "")
    return jsonify(rent.property_json(p))


@bp.post("/api/rent/tenants")
@login_required
@rate_limit(120, 600, scope="rent_add")
def add_tenant():
    data = json_body()
    rows = data.get("tenants") if isinstance(data.get("tenants"), list) else [data]
    if len(rows) > 200:
        raise ApiError("Add up to 200 tenants at a time.")
    u = current_user()
    payloads = [_tenant_payload(r) for r in rows]
    if rent.limited(u) and rent.active_count(u["id"]) + len(payloads) > rent.FREE_TENANTS:
        raise ApiError(f"The free plan covers {rent.FREE_TENANTS} tenants. Upgrade to Kitna Rent Pro to add more.", 402)
    ids = [rent.add_tenant(u, p, commit=False) for p in payloads]
    get_db().commit()
    analytics.track(u["id"], "tenant_added", "bulk" if len(ids) > 1 else "one")
    return jsonify({"ids": ids}), 201


@bp.patch("/api/rent/tenants/<int:tenant_id>")
@login_required
def edit_tenant(tenant_id):
    u = current_user()
    t = rent.get_tenant(u["id"], tenant_id)
    data = json_body()
    fields = _tenant_payload(data, partial=True)
    if data.get("left") is True:
        fields["status"] = "left"
        fields["left_month"] = rent.valid_month(data.get("left_month") or rent.month_of(clock.today()), "Last month")
    elif data.get("left") is False:
        if t["status"] == "left" and rent.limited(u) and rent.active_count(u["id"]) >= rent.FREE_TENANTS:
            raise ApiError(f"The free plan covers {rent.FREE_TENANTS} tenants. Upgrade to bring this tenant back.", 402)
        fields["status"], fields["left_month"] = "active", None
    if not fields:
        raise ApiError("Nothing to change.")
    cols = ", ".join(f"{k} = ?" for k in fields)  # keys come from the whitelist above
    get_db().execute(f"UPDATE rent_tenants SET {cols} WHERE id = ? AND user_id = ?", (*fields.values(), tenant_id, u["id"]))
    get_db().commit()
    return jsonify({"ok": True})


@bp.delete("/api/rent/tenants/<int:tenant_id>")
@login_required
def delete_tenant(tenant_id):
    u = current_user()
    rent.get_tenant(u["id"], tenant_id)
    get_db().execute("DELETE FROM rent_tenants WHERE id = ? AND user_id = ?", (tenant_id, u["id"]))
    get_db().commit()
    return jsonify({"ok": True})


@bp.get("/api/rent/tenants/<int:tenant_id>")
@login_required
def tenant_detail(tenant_id):
    u = current_user()
    t = rent.get_tenant(u["id"], tenant_id)
    p = rent.get_property(u["id"])
    pays = rent.payments_of(t["id"])
    st = rent.state(t, p["due_day"], payments=pays)
    link = f"{_base()}/r/{t['token']}"
    lang = u["lang"] if "lang" in u.keys() else "en"
    phone = rent.wa_phone(t["phone"])
    return jsonify({**rent.tenant_json(t, st, _base()),
                    "payments": [{"id": x["id"], "amount": x["amount"] / 100, "date": x["date"], "method": x["method"],
                                  "how": x["how"]} for x in reversed(pays)],
                    "reminder": rent.remind_text(p, t, st, link, lang), "wa_phone": phone})


@bp.post("/api/rent/tenants/<int:tenant_id>/payments")
@login_required
def add_payment(tenant_id):
    data = json_body()
    amount = parse_amount(data.get("amount"), "Amount")
    day = parse_date(data.get("date")) if data.get("date") else clock.today().isoformat()
    rent.record_manual(current_user()["id"], tenant_id, amount, day, data.get("method") or "cash")
    analytics.track(current_user()["id"], "rent_marked", data.get("method") or "cash")
    return jsonify({"ok": True}), 201


@bp.delete("/api/rent/payments/<int:payment_id>")
@login_required
def delete_payment(payment_id):
    rent.delete_payment(current_user()["id"], payment_id)
    return jsonify({"ok": True})


@bp.post("/api/rent/assign")
@login_required
def assign():
    data = json_body()
    u = current_user()
    try:
        tx_id = int(data.get("transaction_id"))
    except (TypeError, ValueError):
        raise ApiError("Which payment?")
    if data.get("not_rent"):
        rent.not_rent(u["id"], tx_id)
        return jsonify({"ok": True})
    try:
        tenant_id = int(data.get("tenant_id"))
    except (TypeError, ValueError):
        raise ApiError("Whose rent is it?")
    rent.assign(u["id"], tx_id, tenant_id)
    analytics.track(u["id"], "rent_marked", "tapped")
    return jsonify({"ok": True})


@bp.post("/api/rent/reminded/<int:tenant_id>")
@login_required
def reminded(tenant_id):
    rent.get_tenant(current_user()["id"], tenant_id)
    analytics.track(current_user()["id"], "rent_reminded", "")
    return jsonify({"ok": True})


# ─── The tenant's own page: no sign-in, one secret link per tenant ───
@bp.get("/api/r/<token>")
@rate_limit(60, 60, scope="tenant_view")
def tenant_view(token):
    t = rent.by_token(token)
    if t is None:
        raise ApiError("This link isn't valid any more. Ask your PG owner for a new one.", 404)
    resp = jsonify(rent.public_view(t))
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


@bp.get("/api/r/<token>/qr.svg")
@rate_limit(60, 60, scope="tenant_qr")
def tenant_qr(token):
    t = rent.by_token(token)
    if t is None:
        raise ApiError("Not found.", 404)
    v = rent.public_view(t)
    if not v["upi_id"]:
        raise ApiError("The owner hasn't added a UPI ID yet.", 404)
    import io

    import qrcode
    import qrcode.image.svg

    amount = v["balance"] if v["balance"] > 0 else None
    img = qrcode.make(rent.upi_qr_link(v["upi_id"], v["property"], amount), image_factory=qrcode.image.svg.SvgPathImage,
                      box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    from flask import Response

    return Response(buf.getvalue(), mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})
