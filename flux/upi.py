"""UPI helpers based on NPCI's UPI Linking Specification.

Kitna never moves money. It reads a UPI QR / link, runs the pre-spend check,
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

# Merchant Category Codes -> Kitna categories (most common in India)
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
    "gpay": {"name": "Google Pay", "ios": "gpay://upi/pay?", "open_ios": "gpay://", "android": "com.google.android.apps.nbu.paisa.user"},
    "phonepe": {"name": "PhonePe", "ios": "phonepe://pay?", "open_ios": "phonepe://", "android": "com.phonepe.app"},
    "paytm": {"name": "Paytm", "ios": "paytmmp://pay?", "open_ios": "paytmmp://", "android": "net.one97.paytm"},
    "bhim": {"name": "BHIM", "ios": "bhim://upi/pay?", "open_ios": "bhim://", "android": "in.org.npci.upiapp"},
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


# Fields a shop's QR may carry that the UPI app checks (signature etc.).
# They must reach the UPI app exactly as printed on the QR.
MERCHANT_KEYS = ("pa", "pn", "mc", "tr", "tn", "am", "mam", "cu", "url", "mode", "purpose", "orgid", "sign",
                 "mid", "msid", "mtid", "tid", "qrmedium", "invoiceno", "invoicedate", "gstin", "gstbrkup",
                 "ver", "category")


def _qs(params):
    return "&".join(f"{k}={quote(str(v), safe='@.-_')}" for k, v in params)


def original_params(raw):
    """The query of a scanned upi:// code as (key, value) pairs, in order, keys lower-cased."""
    raw = (raw or "").strip()
    if not raw.lower().startswith("upi://"):
        return []
    out = []
    for pair in urlsplit(raw).query.split("&"):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        k = k.strip().lower()
        if k in MERCHANT_KEYS and k not in dict(out):
            out.append((k, unquote(v).strip()))
    return out


def build_links(pa, pn, amount, raw_code=None):
    """Return a generic upi:// link plus app-specific links.

    GPay, PhonePe and others refuse links that look tampered with. So:
    - a shop's QR is passed on exactly as scanned (only the amount is filled in if the QR had none);
    - a person's UPI ID gets the bare minimum: pa, pn, am, cu. No reference or note added by Kitna,
      because a made-up 'tr' makes GPay decline person-to-person payments.
    """
    if not valid_vpa(pa):
        raise ApiError("Invalid UPI ID.")
    amt = parse_amount_str(amount)
    orig = original_params(raw_code)
    od = dict(orig)
    mc = re.sub(r"\D", "", od.get("mc", ""))
    if orig and od.get("pa", "").lower() == pa.lower() and mc and mc != "0000":
        params = [(k, v) for k, v in orig if k != "am"]
        params.insert(min(3, len(params)), ("am", od.get("am") or f"{amt:.2f}"))
        if "cu" not in od:
            params.append(("cu", "INR"))
    else:
        params = [("pa", pa), ("pn", pn or pa.split("@")[0]), ("am", f"{amt:.2f}"), ("cu", "INR")]
    query = _qs(params)
    links = {"generic": f"upi://pay?{query}", "apps": []}
    for key, app in APPS.items():
        links["apps"].append({
            "id": key,
            "name": app["name"],
            "android": f"intent://pay?{query}#Intent;scheme=upi;package={app['android']};end",
            "ios": app["ios"] + query,
            # Just opens the app (its own scanner / home). The payment is made there, the normal way.
            "open_android": f"intent:#Intent;action=android.intent.action.MAIN;category=android.intent.category.LAUNCHER;package={app['android']};end",
            "open_ios": app["open_ios"],
        })
    return links
