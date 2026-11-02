"""UPI app / bank app push notification → Transaction.

Notifications are short and come with a title + body, e.g.
  GPay      title "₹250 paid to Swiggy"            body "Paid from HDFC Bank •• 1234"
  PhonePe   title "Paid ₹250 to Swiggy"             body "UPI ref 512345678901"
  Paytm     title "Payment Successful"               body "Rs.250 paid to Swiggy from Paytm Payments Bank"
  Received  title "₹500 received from Rahul Kumar"   body "Credited to SBI •• 9876"
Bank apps often post the same text as their SMS, so we fall back to the SMS parser.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from . import _common as c
from .categorize import categorize
from .model import Transaction
from .sms import SKIP_RE, parse_sms

PACKAGES = {
    "com.google.android.apps.nbu.paisa.user": "Google Pay",
    "com.phonepe.app": "PhonePe",
    "net.one97.paytm": "Paytm",
    "in.org.npci.upiapp": "BHIM",
    "in.amazon.mShop.android.shopping": "Amazon Pay",
    "com.dreamplug.androidapp": "CRED",
    "money.super.payments": "super.money",
    "com.whatsapp": "WhatsApp Pay",
    "com.csam.icici.bank.imobile": "ICICI iMobile",
    "com.snapwork.hdfc": "HDFC Bank",
    "com.sbi.lotusintouch": "YONO SBI",
    "com.axis.mobile": "Axis Mobile",
    "com.msf.kbank.mobile": "Kotak",
    # Bank SMS also arrive as notifications from the SMS app; parsed with the SMS rules.
    "com.google.android.apps.messaging": "Messages",
    "com.samsung.android.messaging": "Samsung Messages",
}

PAID_RE = [
    re.compile(c.CURRENCY + r"\s*([\d,]+(?:\.\d{1,2})?)\s+(?:paid|sent)\s+to\s+(.+?)(?:\s+(?:from|via|using|on)\b|[.•]|$)", re.I),
    re.compile(r"(?:paid|sent)\s+" + c.CURRENCY + r"\s*([\d,]+(?:\.\d{1,2})?)\s+to\s+(.+?)(?:\s+(?:from|via|using|on)\b|[.•]|$)", re.I),
    re.compile(r"payment to\s+(.+?)\s+(?:successful|succeeded|completed|done)", re.I),
    re.compile(r"(?:payment of|you paid)\s+" + c.CURRENCY + r"\s*([\d,]+(?:\.\d{1,2})?)\s+to\s+(.+?)(?:\s+(?:is|was|from|via)\b|[.•]|$)", re.I),
]
RECEIVED_RE = [
    re.compile(c.CURRENCY + r"\s*([\d,]+(?:\.\d{1,2})?)\s+received\s+from\s+(.+?)(?:\s+(?:in|to|on)\b|[.•]|$)", re.I),
    re.compile(r"(?:received|got)\s+" + c.CURRENCY + r"\s*([\d,]+(?:\.\d{1,2})?)\s+from\s+(.+?)(?:\s+(?:in|to|on)\b|[.•]|$)", re.I),
    re.compile(r"(.+?)\s+(?:sent|paid)\s+you\s+" + c.CURRENCY + r"\s*([\d,]+(?:\.\d{1,2})?)", re.I),
]


def parse_notification(title: str, body: str = "", package: str = "", today: Optional[date] = None) -> Optional[Transaction]:
    text = re.sub(r"\s+", " ", f"{title or ''}. {body or ''}").strip(" .")
    if not text or SKIP_RE.search(text):
        return None
    app = PACKAGES.get(package, "")
    direction, amount, who = None, None, ""
    for rx in PAID_RE:
        m = rx.search(text)
        if m:
            if m.lastindex == 1:  # "Payment to X successful": amount is elsewhere in the text
                direction, amount, who = "debit", c.find_amount(text), m.group(1)
            else:
                direction, amount, who = "debit", c.to_decimal(m.group(1)), m.group(2)
            break
    if direction is None:
        for i, rx in enumerate(RECEIVED_RE):
            m = rx.search(text)
            if m:
                if i == 2:
                    who, amount = m.group(1), c.to_decimal(m.group(2))
                else:
                    amount, who = c.to_decimal(m.group(1)), m.group(2)
                direction = "credit"
                break
    if direction is None or amount is None:
        tx = parse_sms(text, today)  # bank apps reuse their SMS wording
        if tx:
            tx.source = "notification"
            tx.extra["app"] = app
        return tx
    vpa = c.find_vpa(text)
    merchant = c.clean_merchant(who) or (c.clean_merchant(vpa) if vpa else "")
    category, conf, reason = categorize(f"{merchant} {vpa or ''} {text}", direction)
    return Transaction(
        direction=direction, amount=amount, source="notification", raw=text[:500], merchant=merchant, vpa=vpa,
        channel="UPI", account_last4=c.find_account(text), reference=c.find_reference(text),
        balance=c.find_balance(text), txn_date=today or date.today(),
        is_cashback=direction == "credit" and bool(c.CASHBACK_RE.search(text)),
        is_refund=direction == "credit" and bool(c.REFUND_RE.search(text)),
        category=category, category_confidence=conf, category_reason=reason, extra={"app": app},
    )
