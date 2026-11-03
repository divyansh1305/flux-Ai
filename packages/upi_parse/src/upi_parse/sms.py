"""Bank SMS / bank-app alert → Transaction.

Covers the common formats of SBI, HDFC, ICICI, Axis, Kotak, PNB, BoB, Canara, IDFC First,
Yes Bank and Paytm Payments Bank. Promotional messages, OTPs, payment *requests*,
upcoming-debit reminders and bill-due notices return None.
"""
from __future__ import annotations

import re
from datetime import date
from typing import List, Optional

from . import _common as c
from .categorize import categorize
from .model import Transaction

DEBIT_RE = re.compile(r"\b(debited|sent|spent|paid|withdrawn|withdrawal|purchase|deducted|dr|debit|transferred|"
                      r"for using your|made\s+a\s+(?:upi\s+)?payment)\b", re.I)
CREDIT_RE = re.compile(r"\b(credited|received|deposited|refund(?:ed)?|cr|credit|added)\b", re.I)
SKIP_RE = re.compile(
    r"\b(otp|one[- ]time password|verification code|do not share|"
    r"offer|discount|cashback upto|cashback up to|win\b|loan|pre-?approved|apply now|limited period|"
    r"due date|minimum (?:amount )?due|bill (?:is )?due|statement (?:is )?generated|"
    r"will be debited|is due on|scheduled|reminder|"
    r"has requested|requested money|collect request|payment request|approve the request|"
    r"failed|declined|unsuccessful|could not be processed)\b", re.I)

MERCHANT_PATTERNS = [
    re.compile(r"\bto\s+vpa\s+([^\s(,]+)", re.I),
    re.compile(r"\bfrom\s+vpa\s+([^\s(,]+)", re.I),
    re.compile(r"\btrf to\s+(.+?)(?:\s+(?:ref\w*|on|upi)\b|\.|$)", re.I),
    re.compile(r";\s*(.+?)\s+credited", re.I),
    re.compile(r"upi/(?:p2[ma]|dr|cr)/\d+/([^/\s]+)", re.I),
    re.compile(r"\binfo[:\s]+(?:upi/)?([^/\s.]+)", re.I),
    re.compile(r"\btowards\s+(?!upi/)(.+?)\s+(?:has|is|was|on|from|for|ref\w*|\.)", re.I),
    re.compile(r"\bto\s+(?!your|you|a/?c|acct|account)(.+?)\s+(?:on|for|ref\w*|upi|via|using|avl|\(|\.)", re.I),
    re.compile(r"\bat\s+(.+?)\s+(?:on|ref|via|using|txn|avl|\.)", re.I),
    re.compile(r"\b(?:by|from)\s+(?!a/?c|acct|account|your|hdfc|sbi|icici|axis|kotak|pnb|bank)(.+?)"
               r"\s+(?:on|ref|upi|via|avl|\(|\.|$)", re.I),
]


def _merchant(text: str) -> str:
    for rx in MERCHANT_PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        cand = m.group(1).strip(" .,:;-()")
        if not cand or re.fullmatch(r"[\dXx*]+", cand) or len(cand) > 60:
            continue
        name = c.clean_merchant(cand)
        if name:
            return name
    return ""


def parse_sms(text: str, today: Optional[date] = None) -> Optional[Transaction]:
    """Parse one bank SMS. Returns None for anything that isn't a completed debit/credit."""
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) < 15 or SKIP_RE.search(t):
        return None
    amount = c.find_amount(t)
    if amount is None:
        return None
    d, cr = DEBIT_RE.search(t), CREDIT_RE.search(t)
    if not d and not cr:
        return None
    # "Credit Card" names the card, it isn't money coming in.
    cr = CREDIT_RE.search(re.sub(r"credit\s*card", "card", t, flags=re.I))
    if cr and re.search(r"credit\s*card", t, re.I):
        cr = CREDIT_RE.search(re.sub(r"credit\s*card", "xxxxxx card", t, flags=re.I))
    if not d and not cr:
        return None
    # The first verb describes *your* account: "debited … SWIGGY credited" is a debit.
    direction = "debit" if d and (not cr or d.start() < cr.start()) else "credit"
    vpa = c.find_vpa(t)
    merchant = _merchant(t) or (c.clean_merchant(vpa) if vpa else "")
    is_cashback = bool(c.CASHBACK_RE.search(t)) and direction == "credit"
    is_refund = bool(c.REFUND_RE.search(t)) and direction == "credit"
    category, conf, reason = categorize(f"{merchant} {vpa or ''} {t}", direction)
    return Transaction(
        direction=direction, amount=amount, source="sms", raw=t[:500], merchant=merchant, vpa=vpa,
        channel=c.find_channel(t), account_last4=c.find_account(t), reference=c.find_reference(t),
        balance=c.find_balance(t), txn_date=c.find_date(t, today), is_cashback=is_cashback, is_refund=is_refund,
        category=category, category_confidence=conf, category_reason=reason,
    )


def split_messages(blob: str, limit: int = 500) -> List[str]:
    """Split pasted text containing several SMS into individual messages."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", blob or "") if p.strip()]
    out: List[str] = []
    for p in parts:
        lines = [ln.strip() for ln in p.splitlines() if ln.strip()]
        if len(lines) > 1 and all(c.AMOUNT_RE.search(ln) for ln in lines):
            out.extend(lines)
        else:
            out.append(" ".join(lines))
    return out[:limit]
