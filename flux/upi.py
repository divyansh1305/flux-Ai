"""UPI helpers based on NPCI's UPI Linking Specification.

Flux never moves money. It reads a UPI QR / link, runs the pre-spend check,
then hands a *pre-filled* payment request to the user's own UPI app
(GPay, PhonePe, Paytm, BHIM…), where the user enters their PIN.
That's why no NPCI/TPAP licence is needed.
"""
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .security import ApiError

VPA_RE = re.compile(r"^[A-Za-z0-9.\-_]{2,256}@[A-Za-z][A-Za-z0-9.\-]{1,63}$")
MAX_UPI_AMOUNT = Decimal("100000")  # standard per-transaction UPI limit (₹1 lakh)

# Merchant Category Codes -> Flux categories (most common in India)
MCC_CATEGORIES = {
    "5811": "Food & Dining", "5812": "Food & Dining", "5813": "Food & Dining", "5814": "Food & Dining",
    "5411": "Groceries", "5422": "Groceries", "5441": "Groceries", "5451": "Groceries", "5499": "Groceries",
    "4111": "Transport", "4121": "Transport", "4131": "Transport", "4789": "Transport", "5541": "Transport",
    "5542": "Transport", "7523": "Transport", "4112": "Travel", "4511": "Travel", "7011": "Travel", "4722": "Travel",
    "5311": "Shopping", "5651": "Shopping", "5691": "Shopping", "5699": "Shopping", "5732": "Shopping",
    "5945": "Shopping", "5999": "Shopping", "5399": "Shopping", "5661": "Shopping", "5941": "Shopping",
    "4814": "Bills & Utilities", "4899": "Bills & Utilities", "4900": "Bills & Utilities", "4816": "Subscriptions",
    "5815": "Subscriptions", "5816": "Entertainment", "5817": "Subscriptions", "5818": "Subscriptions",
    "7832": "Entertainment", "7922": "Entertainment", "7996": "Entertainment", "7999": "Entertainment",
    "5912": "Health", "8011": "Health", "8021": "Health", "8062": "Health", "8071": "Health", "8099": "Health",
    "7997": "Health", "8211": "Education", "8220": "Education", "8299": "Education", "5942": "Education",
    "5943": "Education", "7230": "Personal Care", "7298": "Personal Care", "6513": "Rent",
}

# How to open a specific UPI app with the same request.
APPS = {
    "gpay": {"name": "Google Pay", "ios": "gpay://upi/pay?", "android": "com.google.android.apps.nbu.paisa.user"},
    "phonepe": {"name": "PhonePe", "ios": "phonepe://pay?", "android": "com.phonepe.app"},
    "paytm": {"name": "Paytm", "ios": "paytmmp://pay?", "android": "net.one97.paytm"},
    "bhim": {"name": "BHIM", "ios": "bhim://upi/pay?", "android": "in.org.npci.upiapp"},
}


def valid_vpa(vpa):
    return bool(vpa) and bool(VPA_RE.match(vpa))


def parse_amount_str(value):
    if value in (None, ""):
        return None
    try:
        amt = Decimal(str(value).strip())
    except InvalidOperation:
        raise ApiError("The QR code has an invalid amount.")
    if amt <= 0 or amt > MAX_UPI_AMOUNT:
        raise ApiError("UPI payments must be between ₹0.01 and ₹1,00,000.")
    return amt.quantize(Decimal("0.01"))


def parse_upi_uri(text):
    """Parse 'upi://pay?pa=...&pn=...' (from a QR code or link). Raises ApiError if invalid."""
    raw = (text or "").strip()
    if len(raw) > 1000:
        raise ApiError("That code is too long to be a UPI QR.")
    if not raw.lower().startswith("upi://"):
        if valid_vpa(raw):  # someone typed / scanned a bare UPI ID
            return {"pa": raw.lower(), "pn": "", "am": None, "tn": "", "mc": "", "tr": "", "is_merchant": False}
        raise ApiError("This isn't a UPI QR code. Point the camera at a UPI QR (GPay, PhonePe, Paytm, BHIM…).")
    parts = urlsplit(raw)
    if parts.netloc.lower() not in ("pay", "mandate", ""):
        raise ApiError("Only UPI payment QR codes are supported.")
    q = {k.lower(): unquote(v[0]).strip() for k, v in parse_qs(parts.query, keep_blank_values=True).items() if v}
    pa = q.get("pa", "")
    if not valid_vpa(pa):
        raise ApiError("This QR code doesn't contain a valid UPI ID.")
    if q.get("cu") and q["cu"].upper() != "INR":
        raise ApiError("Only INR payments are supported.")
    mc = re.sub(r"\D", "", q.get("mc", ""))[:4]
    return {
        "pa": pa.lower(),
        "pn": q.get("pn", "")[:80],
        "am": parse_amount_str(q.get("am")),
        "tn": q.get("tn", "")[:80],
        "mc": mc,
        "tr": q.get("tr", "")[:35],
        "is_merchant": bool(mc) and mc != "0000",
    }


def category_for(parsed, fallback_categorize):
    if parsed.get("mc") in MCC_CATEGORIES:
        return MCC_CATEGORIES[parsed["mc"]], "merchant code"
    text = f"{parsed.get('pn', '')} {parsed.get('pa', '').split('@')[0]}"
    cat, kw = fallback_categorize(text, "expense")
    return cat, ("merchant name" if kw else None)


def build_links(pa, pn, amount, note, tr):
    """Return a generic upi:// link plus app-specific links. All values are validated + percent-encoded."""
    if not valid_vpa(pa):
        raise ApiError("Invalid UPI ID.")
    amt = parse_amount_str(amount)
    params = [("pa", pa), ("pn", pn or pa.split("@")[0]), ("am", f"{amt:.2f}"), ("cu", "INR")]
    if note:
        params.append(("tn", note[:50]))
    if tr:
        params.append(("tr", tr))
    query = "&".join(f"{k}={quote(str(v), safe='@.-_')}" for k, v in params)
    links = {"generic": f"upi://pay?{query}", "apps": []}
    for key, app in APPS.items():
        links["apps"].append({
            "id": key,
            "name": app["name"],
            "android": f"intent://pay?{query}#Intent;scheme=upi;package={app['android']};end",
            "ios": app["ios"] + query,
        })
    return links
