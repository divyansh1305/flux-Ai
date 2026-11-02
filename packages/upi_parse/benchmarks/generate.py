"""Generate the synthetic labelled benchmark (benchmarks/synthetic_v1.jsonl).

Templates mirror the public formats of Indian bank SMS and UPI app notifications.
They are written from the banks' message formats, NOT from the parser's rules, and add
noise (case changes, line breaks, extra words, masked digits) to keep the test honest.

Every record: {"kind": "sms"|"notification"|"narration", "text"/"title"/"body"/"narration",
               "label": {"is_txn", "direction", "amount", "merchant", "category", "reference", "balance"}}
Real-world accuracy must still be measured on real, consented data (see contribute tool in Flux).
"""
import json
import random
from pathlib import Path

R = random.Random(20261102)

MERCHANTS = [  # (display name, vpa handle, category)
    ("Swiggy", "swiggy", "Food & Dining"), ("Zomato", "zomato", "Food & Dining"), ("Dominos", "dominos", "Food & Dining"),
    ("Starbucks", "starbucks", "Food & Dining"), ("Chai Point", "chaipoint", "Food & Dining"), ("KFC", "kfc", "Food & Dining"),
    ("Blinkit", "blinkit", "Groceries"), ("Zepto", "zepto", "Groceries"), ("BigBasket", "bigbasket", "Groceries"),
    ("DMart", "dmart", "Groceries"), ("Uber", "uber", "Transport"), ("Ola", "olacabs", "Transport"),
    ("Rapido", "rapido", "Transport"), ("IRCTC", "irctc", "Transport"), ("Indian Oil", "iocl", "Transport"),
    ("MakeMyTrip", "makemytrip", "Travel"), ("IndiGo", "indigo", "Travel"), ("OYO", "oyo", "Travel"),
    ("Amazon", "amazon", "Shopping"), ("Flipkart", "flipkart", "Shopping"), ("Myntra", "myntra", "Shopping"),
    ("Ajio", "ajio", "Shopping"), ("Croma", "croma", "Shopping"), ("Netflix", "netflix", "Subscriptions"),
    ("Spotify", "spotify", "Subscriptions"), ("Hotstar", "hotstar", "Subscriptions"),
    ("Airtel", "airtel", "Bills & Utilities"), ("Jio", "jio", "Bills & Utilities"),
    ("Tata Power", "tatapower", "Bills & Utilities"), ("BookMyShow", "bookmyshow", "Entertainment"),
    ("PVR", "pvrcinemas", "Entertainment"), ("Apollo Pharmacy", "apollopharmacy", "Health"),
    ("PharmEasy", "pharmeasy", "Health"), ("Cult.fit", "cultfit", "Health"), ("Udemy", "udemy", "Education"),
    ("Unacademy", "unacademy", "Education"), ("Urban Company", "urbancompany", "Personal Care"),
    ("Zerodha", "zerodha", "Investments"), ("Groww", "groww", "Investments"), ("NoBroker", "nobroker", "Rent"),
]
HANDLES = ["icici", "hdfcbank", "ybl", "axl", "paytm", "okaxis", "oksbi", "ibl", "axisbank", "kotak"]
PEOPLE = ["Rahul Kumar", "Priya Sharma", "Aman Verma", "Sneha Gupta", "Rohit Singh", "Neha Yadav"]


def amt(lo=20, hi=4000):
    v = R.choice([R.randint(lo, hi), round(R.uniform(lo, hi), 2), R.randint(lo // 10 + 1, hi // 10) * 10])
    return round(float(v), 2)


def fmt(v, comma=True):
    s = f"{v:,.2f}" if comma else f"{v:.2f}"
    return s if R.random() < 0.8 else s.rstrip("0").rstrip(".")


def ref():
    return str(R.randint(4, 6)) + "".join(str(R.randint(0, 9)) for _ in range(11))


def acct():
    return str(R.randint(1000, 9999))


def date_s():
    d, m = R.randint(1, 28), R.randint(1, 10)
    mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"][m - 1]
    return R.choice([f"{d:02d}-{m:02d}-26", f"{d:02d}/{m:02d}/26", f"{d:02d}-{mon}-26", f"{d:02d}{mon}26",
                     f"{d:02d}-{m:02d}-2026", f"{d} {mon} 2026"])


def noise(t):
    r = R.random()
    if r < 0.12:
        t = t.upper()
    elif r < 0.2:
        t = t.replace(". ", ".\n")
    elif r < 0.26:
        t = "  " + t.replace(" ", "  ", 2)
    return t


def debit_sms(name, handle, cat):
    a, rf, ac, bal = amt(), ref(), acct(), amt(500, 60000)
    vpa = f"{handle}@{R.choice(HANDLES)}"
    with_bal = R.random() < 0.5
    bal_txt = f" Avl Bal Rs {fmt(bal)}." if with_bal else ""
    tpl = R.choice([
        f"Rs.{fmt(a)} debited from A/c XX{ac} on {date_s()} to VPA {vpa} (UPI Ref No {rf}).{bal_txt} Not you? Call 1800",
        f"Sent Rs.{fmt(a)} From HDFC Bank A/C *{ac} To {name.upper()} On {date_s()} Ref {rf} Not You? Call 18002586161",
        f"ICICI Bank Acct XX{ac[-3:]} debited for Rs {fmt(a)} on {date_s()}; {name.upper()} credited. UPI:{rf}. Call 18002662 for dispute",
        f"Dear UPI user A/C X{ac} debited by {fmt(a, False)} on date {date_s()} trf to {name.upper()} Refno {rf}. If not u? call 1800111109 -SBI",
        f"INR {fmt(a)} debited A/c no. XX{ac} {date_s()} 10:22:33 UPI/P2M/{rf}/{name.upper()}{bal_txt} Not you? SMS BLOCK -Axis Bank",
        f"Sent Rs.{fmt(a)} from Kotak Bank AC X{ac} to {vpa} on {date_s()}.UPI Ref {rf}. Not you, kotak.com/fraud",
        f"Your a/c no. XXXXXXXX{ac} is debited for Rs.{fmt(a)} on {date_s()} and credited to {vpa} (UPI Ref no {rf}).{bal_txt} -PNB",
        f"Rs {fmt(a)} spent on your card ending {ac} at {name.upper()} on {date_s()}.{bal_txt} Not you? Call us",
        f"Your A/C XXXXX{ac} has a debit by transfer of Rs {fmt(a)} on {date_s()} to {name}. UPI Ref {rf}.{bal_txt} -BoB",
    ])
    card = "card ending" in tpl
    return {"kind": "sms", "text": noise(tpl), "label": {
        "is_txn": True, "direction": "debit", "amount": a, "merchant": name, "category": cat,
        "reference": None if card else rf, "balance": bal if with_bal and bal_txt in tpl else None}}


def credit_sms():
    a, rf, ac = amt(100, 60000), ref(), acct()
    r = R.random()
    if r < 0.3:
        tpl, merchant, cat, refv = (f"Dear Customer, INR {fmt(a)} credited to your A/c XX{ac} on {date_s()} by NEFT from ACME TECH SALARY. Avl Bal INR {fmt(a + 1000)}",
                                    "Acme Tech", "Salary", None)
        bal = round(a + 1000, 2)
    elif r < 0.55:
        p = R.choice(PEOPLE)
        tpl, merchant, cat, refv = (f"Rs.{fmt(a)} credited to A/c XX{ac} on {date_s()} from VPA {p.split()[0].lower()}@oksbi (UPI Ref No {rf}). -SBI",
                                    p.split()[0], "Other Income", rf)
        bal = None
    elif r < 0.75:
        a = amt(5, 150)
        tpl, merchant, cat, refv = (f"Rs {fmt(a)} credited to your a/c XX{ac} as cashback from {R.choice(['PhonePe', 'Paytm', 'Amazon Pay'])} on {date_s()}",
                                    None, "Cashback", None)
        bal = None
    elif r < 0.9:
        tpl, merchant, cat, refv = (f"Refund of Rs.{fmt(a)} from {R.choice(['Flipkart', 'Amazon', 'Myntra'])} has been credited to your a/c XX{ac} on {date_s()}. Ref {rf}",
                                    None, "Refund", rf)
        bal = None
    else:
        a = amt(5, 400)
        tpl, merchant, cat, refv = (f"Interest of Rs {fmt(a)} credited to your Savings A/c XX{ac} on {date_s()}. -Kotak", None, "Interest", None)
        bal = None
    return {"kind": "sms", "text": noise(tpl), "label": {"is_txn": True, "direction": "credit", "amount": a,
                                                         "merchant": merchant, "category": cat, "reference": refv, "balance": bal}}


def negative_sms():
    a, ac = amt(), acct()
    tpl = R.choice([
        f"{R.randint(100000, 999999)} is your OTP for transaction of Rs {fmt(a)} at AMAZON. Do not share it with anyone.",
        f"Get cashback upto Rs 500 on your next recharge! Offer valid till Sunday. T&C apply",
        f"Your credit card bill of Rs {fmt(a)} is due on 10-11-26. Minimum due Rs {fmt(a / 20)}. Pay now",
        f"{R.choice(PEOPLE)} has requested money from you on Google Pay. Amount: Rs {fmt(a)}. Ignore if unknown",
        f"Rs {fmt(a)} will be debited from your A/c XX{ac} on 05-11-26 towards NETFLIX autopay mandate.",
        f"Transaction of Rs {fmt(a)} at FLIPKART failed. Any amount debited will be refunded in 5-7 days.",
        f"Congratulations! You are pre-approved for a personal loan of Rs 5,00,000. Apply now",
        f"Your payment of Rs {fmt(a)} to SWIGGY was declined due to insufficient balance. -HDFC Bank",
        f"Dear customer, your statement for card XX{ac} is generated. Total due Rs {fmt(a)}.",
    ])
    return {"kind": "sms", "text": noise(tpl), "label": {"is_txn": False}}


def notification(name, handle, cat):
    a, rf, ac = amt(), ref(), acct()
    pkg, title, body = R.choice([
        ("com.google.android.apps.nbu.paisa.user", f"₹{fmt(a)} paid to {name}", f"Paid from HDFC Bank •• {ac}"),
        ("com.phonepe.app", f"Paid ₹{fmt(a)} to {name}", f"UPI Ref No. {rf}"),
        ("net.one97.paytm", "Payment Successful", f"Rs.{fmt(a)} paid to {name} from Paytm Payments Bank"),
        ("com.google.android.apps.nbu.paisa.user", f"You paid ₹{fmt(a)} to {name}", "Tap to view details"),
    ])
    return {"kind": "notification", "package": pkg, "title": title, "body": body, "label": {
        "is_txn": True, "direction": "debit", "amount": a, "merchant": name, "category": cat,
        "reference": rf if "Ref" in body else None, "balance": None}}


def received_notification():
    a, p = amt(50, 5000), R.choice(PEOPLE)
    title = R.choice([f"₹{fmt(a)} received from {p}", f"{p} sent you ₹{fmt(a)}", f"Received ₹{fmt(a)} from {p}"])
    return {"kind": "notification", "package": "com.phonepe.app", "title": title, "body": "Credited to SBI •• 9876",
            "label": {"is_txn": True, "direction": "credit", "amount": a, "merchant": p, "category": "Other Income",
                      "reference": None, "balance": None}}


def narration(name, handle, cat):
    a, rf = amt(), ref()
    vpa = f"{handle}@{R.choice(HANDLES)}"
    text = R.choice([f"UPI/DR/{rf}/{name.upper()}/YESB/{vpa}/Payment", f"UPI-{name.upper()}-{vpa}-HDFC0001234-{rf}-PAYMENT",
                     f"POS {name.upper()} MUMBAI", f"UPI/{rf}/{name.upper()}/{vpa}/ICICI"])
    return {"kind": "narration", "narration": text, "amount": a, "direction": "debit", "label": {
        "is_txn": True, "direction": "debit", "amount": a, "merchant": name, "category": cat,
        "reference": None if text.startswith("POS") else rf, "balance": None}}


def main():
    rows = []
    for _ in range(520):
        rows.append(debit_sms(*R.choice(MERCHANTS)))
    for _ in range(180):
        rows.append(credit_sms())
    for _ in range(160):
        rows.append(negative_sms())
    for _ in range(160):
        rows.append(notification(*R.choice(MERCHANTS)))
    for _ in range(40):
        rows.append(received_notification())
    for _ in range(160):
        rows.append(narration(*R.choice(MERCHANTS)))
    R.shuffle(rows)
    out = Path(__file__).with_name("synthetic_v1.jsonl")
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
