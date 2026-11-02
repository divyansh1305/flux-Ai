"""UPI QR codes and payment links (NPCI UPI Linking Specification).

    parse_upi_uri("upi://pay?pa=shop@okaxis&pn=Chai%20Point&am=60&mc=5812")
    build_upi_uri("shop@okaxis", "Chai Point", "60.00", note="tea")
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import parse_qs, quote, unquote, urlsplit

VPA_RE = re.compile(r"^[A-Za-z0-9.\-_]{2,256}@[A-Za-z][A-Za-z0-9.\-]{1,63}$")
MAX_UPI_AMOUNT = Decimal("100000")


class UPIError(ValueError):
    pass


@dataclass
class UPIRequest:
    vpa: str
    name: str = ""
    amount: Optional[Decimal] = None
    note: str = ""
    mcc: str = ""
    reference: str = ""

    @property
    def is_merchant(self) -> bool:
        return bool(self.mcc) and self.mcc != "0000"


def valid_vpa(vpa: str) -> bool:
    return bool(vpa) and bool(VPA_RE.match(vpa))


def _amount(value) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        amt = Decimal(str(value).strip())
    except InvalidOperation:
        raise UPIError("Invalid amount.")
    if amt <= 0 or amt > MAX_UPI_AMOUNT:
        raise UPIError("UPI amounts must be between ₹0.01 and ₹1,00,000.")
    return amt.quantize(Decimal("0.01"))


def parse_upi_uri(text: str) -> UPIRequest:
    raw = (text or "").strip()
    if len(raw) > 1000:
        raise UPIError("Too long to be a UPI QR code.")
    if not raw.lower().startswith("upi://"):
        if valid_vpa(raw):
            return UPIRequest(vpa=raw.lower())
        raise UPIError("Not a UPI QR code.")
    parts = urlsplit(raw)
    if parts.netloc.lower() not in ("pay", "mandate", ""):
        raise UPIError("Only UPI payment codes are supported.")
    q = {k.lower(): unquote(v[0]).strip() for k, v in parse_qs(parts.query, keep_blank_values=True).items() if v}
    if not valid_vpa(q.get("pa", "")):
        raise UPIError("No valid UPI ID in this code.")
    if q.get("cu") and q["cu"].upper() != "INR":
        raise UPIError("Only INR is supported.")
    return UPIRequest(vpa=q["pa"].lower(), name=q.get("pn", "")[:80], amount=_amount(q.get("am")),
                      note=q.get("tn", "")[:80], mcc=re.sub(r"\D", "", q.get("mc", ""))[:4], reference=q.get("tr", "")[:35])


def build_upi_uri(vpa: str, name: str, amount, note: str = "", reference: str = "") -> str:
    if not valid_vpa(vpa):
        raise UPIError("Invalid UPI ID.")
    amt = _amount(amount)
    if amt is None:
        raise UPIError("Amount is required.")
    params = [("pa", vpa), ("pn", name or vpa.split("@")[0]), ("am", f"{amt:.2f}"), ("cu", "INR")]
    if note:
        params.append(("tn", note[:50]))
    if reference:
        params.append(("tr", reference))
    return "upi://pay?" + "&".join(f"{k}={quote(str(v), safe='@.-_')}" for k, v in params)
