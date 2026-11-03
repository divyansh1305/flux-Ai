"""Shared helpers: amounts, dates, references, account numbers, merchant clean-up."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

CURRENCY = r"(?:rs\.?|inr|₹)"
AMOUNT_RE = re.compile(CURRENCY + r"[\s:]*([\d,]+(?:\.\d{1,2})?)", re.I)
BARE_AMOUNT_RE = re.compile(r"\b(?:debited|credited|deducted)\s+(?:by|for|with|of)\s+([\d,]+(?:\.\d{1,2})?)\b", re.I)
BALANCE_RE = re.compile(
    r"(?:avl\.?\s*bal(?:ance)?|avail(?:able)?\.?\s*bal(?:ance)?|a/c\s+bal(?:ance)?|bal(?:ance)?\s*(?:is|:)|"
    r"clear\s+bal(?:ance)?|total\s+bal(?:ance)?)\s*[:\-]?\s*(?:is\s*)?" + CURRENCY + r"?[\s:]*([\d,]+(?:\.\d{1,2})?)", re.I)
REF_RE = re.compile(
    r"(?:upi\s*ref(?:erence)?(?:\s*no\.?|\s*number)?|ref(?:erence)?(?:\s*no\.?|\s*number|\s*id)?|utr(?:\s*no\.?)?|"
    r"rrn|txn\s*id|transaction\s*id|upi)(?:\s+is)?\s*[:#.\-]?\s*(\d{10,16})", re.I)
VPA_RE = re.compile(r"\b([a-z0-9][a-z0-9.\-_]{1,63}@[a-z][a-z0-9]{1,20})\b", re.I)
ACCOUNT_RE = re.compile(r"(?:a/?c|acct|account|card)(?:\s*(?:no\.?|number|ending(?:\s*with)?))?\s*[:.]?\s*[xX*]*(\d{3,4})\b", re.I)
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b"), "dmy"),
    (re.compile(rf"\b(\d{{1,2}})[-\s]?({MONTHS})[a-z]*[-\s,]?\s?(\d{{2,4}})\b", re.I), "dMy"),
    (re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"), "ymd"),
]
CHANNELS = [
    ("UPI", r"\bupi\b|vpa|@[a-z]+\b"), ("NEFT", r"\bneft\b"), ("IMPS", r"\bimps\b"), ("RTGS", r"\brtgs\b"),
    ("ATM", r"\batm\b|cash\s*withdrawal"), ("POS", r"\bpos\b"), ("ACH", r"\bach\b|\bnach\b|e-?mandate|autopay"),
    ("CARD", r"credit\s*card|debit\s*card|\bcard\b"),
]
CASHBACK_RE = re.compile(r"\bcash\s?back\b|\breward(?:s)?\s+(?:credited|received)\b|\bscratch\s*card\b", re.I)
REFUND_RE = re.compile(r"\brefund(?:ed)?\b|\breversal\b|\breversed\b|\bchargeback\b", re.I)


def to_decimal(text: str) -> Optional[Decimal]:
    try:
        value = Decimal(text.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None
    if value <= 0 or value > Decimal("100000000"):
        return None
    return value.quantize(Decimal("0.01"))


def find_amount(text: str) -> Optional[Decimal]:
    """First currency amount that isn't the balance."""
    bal = BALANCE_RE.search(text)
    for m in AMOUNT_RE.finditer(text):
        if bal and bal.start() <= m.start() <= bal.end():
            continue
        value = to_decimal(m.group(1))
        if value is not None:
            return value
    m = BARE_AMOUNT_RE.search(text)
    return to_decimal(m.group(1)) if m else None


def find_balance(text: str) -> Optional[Decimal]:
    m = BALANCE_RE.search(text)
    return to_decimal(m.group(1)) if m else None


UPI_PATH_REF_RE = re.compile(r"\b(?:upi/(?:p2[ma]|dr|cr)/|imps-|upi-?)(\d{12})\b", re.I)


def find_reference(text: str) -> Optional[str]:
    m = REF_RE.search(text) or UPI_PATH_REF_RE.search(text)
    return m.group(1) if m else None


def find_vpa(text: str) -> Optional[str]:
    for m in VPA_RE.finditer(text):
        vpa = m.group(1).lower()
        if not re.search(r"\.(com|in|co|net|org)$", vpa):  # skip email addresses
            return vpa
    return None


def find_account(text: str) -> Optional[str]:
    m = ACCOUNT_RE.search(text)
    return m.group(1)[-4:] if m else None


def find_channel(text: str) -> Optional[str]:
    low = text.lower()
    for name, rx in CHANNELS:
        if re.search(rx, low):
            return name
    return None


def find_date(text: str, today: Optional[date] = None) -> Optional[date]:
    today = today or date.today()
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text):
            try:
                if kind == "dmy":
                    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    y = y + 2000 if y < 100 else y
                    found = date(y, mo, d)
                elif kind == "dMy":
                    d, y = int(m.group(1)), int(m.group(3))
                    y = y + 2000 if y < 100 else y
                    found = date(y, datetime.strptime(m.group(2)[:3].title(), "%b").month, d)
                else:
                    found = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if found.year >= 2000 and (found - today).days <= 1:
                return found
    return None


_SKIP_TOKENS = {
    "upi", "dr", "cr", "neft", "imps", "rtgs", "pos", "ach", "nach", "ecom", "payment", "payments", "txn", "to", "from",
    "p2a", "p2m", "mb", "ib", "ref", "trf", "transfer", "by", "vpa", "mob", "inb", "bil", "onl", "debit", "credit",
    "phone", "paid", "sent", "collect", "request", "app", "d", "tp", "via", "successful", "done",
}
_COMPANY_SUFFIX = {"pvt", "pvt.", "private", "ltd", "ltd.", "limited", "llp", "inc", "inc.", "co", "co."}
_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def clean_merchant(value: str) -> str:
    """'UPI/DR/412345/SWIGGY/YESB/swiggy@ybl' -> 'Swiggy'; 'NEFT CR-ACME TECH' -> 'Acme Tech'."""
    if not value:
        return ""
    parts = [p.strip() for p in re.split(r"[/|\\]|(?<!\w)-|-(?!\w)|\s-\s", value) if p and p.strip()]
    if len(parts) == 1:
        parts = [p.strip() for p in re.split(r"[/|-]", value) if p.strip()]
    for p in parts:
        if "@" in p:
            local = p.split("@")[0]
            if re.fullmatch(r"[\d.]+", local) or len(local) < 3:
                continue
            p = local
        if re.fullmatch(r"[\d\s.:*Xx]+", p) or _IFSC_RE.match(p.upper()) or len(p) < 3:
            continue
        words = [w for w in re.split(r"\s+", p) if w and w.lower().strip(".:") not in _SKIP_TOKENS]
        if not words:
            continue
        name = " ".join(words)
        name = re.sub(r"[._]+", " ", name).strip(" .,:;")
        toks = name.split()
        while len(toks) > 1 and toks[-1].lower() in _COMPANY_SUFFIX:
            toks.pop()
        name = " ".join(toks)
        if len(name) >= 2:
            from .categorize import brand_name

            pretty = " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in name.split())[:40]
            return brand_name(pretty)
    return ""
