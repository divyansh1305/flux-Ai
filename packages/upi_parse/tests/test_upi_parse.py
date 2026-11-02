from datetime import date
from decimal import Decimal
from pathlib import Path
import json

import pytest

from upi_parse import (UPIError, build_upi_uri, categorize, parse_narration, parse_notification, parse_sms,
                       parse_statement_csv, parse_upi_uri, split_messages)

D = Decimal
TODAY = date(2026, 11, 2)


def test_sms_full_extraction():
    t = parse_sms("Rs.250.00 debited from A/c XX1234 on 01-11-26 to VPA swiggy@icici (UPI Ref No 512345678901). "
                  "Avl Bal Rs 9,750.00", today=TODAY)
    assert (t.direction, t.amount, t.merchant, t.vpa) == ("debit", D("250.00"), "Swiggy", "swiggy@icici")
    assert (t.category, t.reference, t.balance, t.account_last4) == ("Food & Dining", "512345678901", D("9750.00"), "1234")
    assert t.txn_date == date(2026, 11, 1) and t.channel == "UPI" and t.category_confidence >= 0.9


@pytest.mark.parametrize("text", [
    "123456 is your OTP for Rs 500 at AMAZON. Do not share.",
    "Rohan has requested money from you. Rs 200",
    "Rs 999 will be debited on 05-11-26 for NETFLIX autopay",
    "Your payment of Rs 300 to ZOMATO failed",
    "Get cashback upto Rs 100 on your first UPI payment",
    "Your card bill of Rs 4,000 is due on 10-11-26",
])
def test_non_transactions_are_ignored(text):
    assert parse_sms(text) is None


def test_credit_card_purchase_is_a_debit():
    t = parse_sms("Thank you for using your Credit Card ending 4321 for Rs. 1,050.00 at AMAZON on 13-10-2026")
    assert t.direction == "debit" and t.merchant == "Amazon" and t.category == "Shopping"


def test_cashback_and_refund_flags():
    cb = parse_sms("Rs 25.00 credited to your a/c XX1234 as cashback from PhonePe")
    assert cb.is_cashback and cb.category == "Cashback"
    rf = parse_sms("Refund of Rs.799.00 from AJIO has been credited to your A/c XX2211. Ref 628866667777")
    assert rf.is_refund and rf.category == "Refund"


def test_notifications():
    t = parse_notification("₹250 paid to Swiggy", "Paid from HDFC Bank •• 1234", "com.google.android.apps.nbu.paisa.user")
    assert t.amount == D("250.00") and t.merchant == "Swiggy" and t.extra["app"] == "Google Pay"
    r = parse_notification("₹500 received from Rahul Kumar", "Credited to SBI •• 9876")
    assert r.direction == "credit" and r.merchant == "Rahul Kumar"
    assert parse_notification("Rohit requested ₹200", "Tap to pay or decline") is None


def test_narration_and_most_specific_brand_wins():
    t = parse_narration("UPI-BUNDL TECHNOLOGIES PVT-swiggy.instamart@icici-ICIC0DC0099-628800009999-UPI", 432, "debit")
    assert t.merchant == "Swiggy" and t.category == "Groceries" and t.reference == "628800009999"


def test_same_payment_from_two_sources_has_same_fingerprint():
    sms = parse_sms("Rs.347.00 debited from A/c XX1 to VPA zomato@hdfc (UPI Ref No 628811112222)")
    stmt = parse_narration("UPI/DR/628811112222/ZOMATO/HDFC/zomato@hdfc", 347, "debit")
    assert sms.fingerprint() == stmt.fingerprint()


def test_statement_csv():
    csv_text = ("Date,Narration,Ref,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
                "01/10/26,UPI-SWIGGY-swiggy@icici-ICIC0001-512345678901,1,01/10/26,245.00,,10000.00\n"
                "02/10/26,NEFT CR-ACME TECH SALARY,2,02/10/26,,30000.00,40000.00\n")
    txs, skipped = parse_statement_csv(csv_text)
    assert [t.direction for t in txs] == ["debit", "credit"] and skipped == 0
    assert txs[0].balance == D("10000.00") and txs[1].category == "Salary"


def test_upi_qr_roundtrip_and_validation():
    req = parse_upi_uri("upi://pay?pa=shop@okaxis&pn=Chai%20%26%20Co&am=60&mc=5812&cu=INR")
    assert req.vpa == "shop@okaxis" and req.amount == D("60.00") and req.is_merchant
    uri = build_upi_uri(req.vpa, req.name, req.amount, note="tea")
    assert uri.startswith("upi://pay?pa=shop@okaxis&pn=Chai%20%26%20Co&am=60.00&cu=INR")
    for bad in ["https://x.com", "upi://pay?pa=bad", "upi://pay?pa=a@b&am=500000", "upi://pay?pa=ab@cd&cu=USD"]:
        with pytest.raises(UPIError):
            parse_upi_uri(bad)


def test_categorize_confidence_levels():
    assert categorize("UPI to netflix", "debit")[1] == 0.95
    assert categorize("Sharma pharmacy", "debit")[0] == "Health"
    assert categorize("random words", "debit") == ("Other", 0.2, "no rule matched")
    assert categorize("anything", "debit", mcc="5411")[0] == "Groceries"


def test_split_messages():
    blob = "Rs 10 debited a/c 1\nRs 20 debited a/c 2\n\nYour OTP is 1"
    assert len(split_messages(blob)) == 3


@pytest.mark.parametrize("name", ["synthetic_v1.jsonl", "heldout_v1.jsonl"])
def test_benchmark_regression(name):
    """Guard against regressions: detection and amount must stay perfect on both sets."""
    from benchmarks_eval import evaluate_file

    r = evaluate_file(Path(__file__).parents[1] / "benchmarks" / name)
    assert r["precision"] == 1.0 and r["recall"] >= 0.99 and r["amount"] == 1.0 and r["category"] >= 0.97


# ─── Anonymisation for shared test cases ─────────────────────
from upi_parse import mask_text  # noqa: E402


def test_mask_removes_people_accounts_phones_and_refs_but_keeps_shape():
    m = mask_text("INR 1,500.00 credited to your A/c no. XXXXXX7788 by IMPS from Amit Verma. Call 9123456789 if not you. Ref 412345678901")
    assert "7788" not in m and "Amit" not in m and "9123456789" not in m and "412345678901" not in m
    assert "INR 1,500.00 credited" in m and "IMPS" in m and "Call" in m


def test_mask_keeps_known_brands_and_hides_personal_vpas():
    assert mask_text("Rs.250 debited to VPA swiggy@icici") == "Rs.250 debited to VPA swiggy@icici"
    assert "user@ybl" in mask_text("Rs.50 sent to 9876543210@ybl")
    assert "user@okaxis" in mask_text("Rs.50 sent to rahul.k@okaxis")


def test_masked_text_still_parses_to_the_same_amount_and_direction():
    raw = "Rs.347.00 debited from A/c XX1234 on 01-11-26 to VPA zomato@hdfc (UPI Ref No 628811112222). Avl Bal Rs 9,653.00"
    a, b = parse_sms(raw), parse_sms(mask_text(raw))
    assert (a.amount, a.direction, a.balance, a.category) == (b.amount, b.direction, b.balance, b.category)
