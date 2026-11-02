"""Bank statement import."""
import io
import os

from flux.api.statement import parse_statement
from flux.categorize import categorize

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_data", "sample_statement.csv")

HDFC_STYLE = """HDFC BANK Ltd.  Statement of account
Account No : XXXX1234

Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance
01/10/26,UPI-SWIGGY-swiggy@icici-ICIC0001-123,0000123,01/10/26,245.00,,10000.00
02/10/26,NEFT CR-ACME TECH SALARY OCT,0000124,02/10/26,,30000.00,40000.00
03/10/26,UPI-UBER INDIA-uber@axis,0000125,03/10/26,"1,180.50",,38819.50
"""

SBI_STYLE = """Txn Date\tValue Date\tDescription\tRef No./Cheque No.\tDebit\tCredit\tBalance
5 Oct 2026\t5 Oct 2026\tTO TRANSFER-UPI/DR/412345/NETFLIX/HDFC/netflix@hdfc\t\t649.00\t\t9000.00
6 Oct 2026\t6 Oct 2026\tBY TRANSFER-INTEREST CREDIT\t\t\t12.00\t9012.00
"""

AMOUNT_STYLE = """Date,Description,Amount,Type
2026-10-07,Blinkit order,520,DR
2026-10-08,Refund from Amazon,300,CR
"""


def test_hdfc_format():
    rows, skipped = parse_statement(HDFC_STYLE)
    assert [r["kind"] for r in rows] == ["expense", "income", "expense"]
    assert rows[0]["category"] == "Food & Dining" and rows[0]["amount"] == 245.0
    assert rows[1]["category"] == "Salary"
    assert rows[2]["amount"] == 1180.5 and rows[2]["category"] == "Transport"
    assert rows[0]["date"] == "2026-10-01"


def test_sbi_tab_format():
    rows, _ = parse_statement(SBI_STYLE)
    assert rows[0]["category"] == "Subscriptions" and rows[0]["amount"] == 649
    assert rows[1]["kind"] == "income" and rows[1]["category"] == "Interest"


def test_amount_and_type_format():
    rows, _ = parse_statement(AMOUNT_STYLE)
    assert rows[0]["kind"] == "expense" and rows[0]["category"] == "Groceries"
    assert rows[1]["kind"] == "income" and rows[1]["category"] == "Refund"


def test_description_column_not_confused_with_credit():
    """Old bug: 'cr' matched inside 'description', so the wrong column was used as credit."""
    rows, _ = parse_statement(AMOUNT_STYLE)
    assert len(rows) == 2


def test_categoriser_accuracy_on_labelled_sample():
    labelled = [
        ("UPI/DR/1/ZOMATO/x", "expense", "Food & Dining"), ("POS DOMINOS PIZZA", "expense", "Food & Dining"),
        ("BLINKIT COMMERCE", "expense", "Groceries"), ("ZEPTO MARKETPLACE", "expense", "Groceries"),
        ("UBER INDIA SYSTEMS", "expense", "Transport"), ("OLA CABS", "expense", "Transport"),
        ("HPCL PETROL PUMP", "expense", "Transport"), ("IRCTC E-TICKET", "expense", "Transport"),
        ("AMAZON PAY INDIA", "expense", "Shopping"), ("FLIPKART INTERNET", "expense", "Shopping"),
        ("MYNTRA DESIGNS", "expense", "Shopping"), ("NETFLIX.COM", "expense", "Subscriptions"),
        ("SPOTIFY INDIA", "expense", "Subscriptions"), ("AIRTEL PREPAID RECHARGE", "expense", "Bills & Utilities"),
        ("JIO RECHARGE", "expense", "Bills & Utilities"), ("BOOKMYSHOW", "expense", "Entertainment"),
        ("PVR CINEMAS", "expense", "Entertainment"), ("APOLLO PHARMACY", "expense", "Health"),
        ("UDEMY COURSE", "expense", "Education"), ("MAKEMYTRIP", "expense", "Travel"),
        ("ATM CASH WITHDRAWAL", "expense", "Transfers"), ("URBAN COMPANY", "expense", "Personal Care"),
        ("MONTHLY RENT TO LANDLORD", "expense", "Rent"), ("STARBUCKS COFFEE", "expense", "Food & Dining"),
        ("NEFT CR SALARY", "income", "Salary"), ("SB INTEREST CREDIT", "income", "Interest"),
        ("REFUND FLIPKART", "income", "Refund"), ("UPWORK ESCROW", "income", "Freelance"),
    ]
    correct = sum(categorize(d, k)[0] == want for d, k, want in labelled)
    accuracy = correct / len(labelled)
    assert accuracy >= 0.9, f"accuracy {accuracy:.0%}"


def test_preview_and_commit_with_dedupe(client, user):
    data = {"file": (io.BytesIO(HDFC_STYLE.encode()), "statement.csv")}
    r = client.post("/api/import/preview", data=data, content_type="multipart/form-data")
    assert r.status_code == 200, r.json
    rows = r.json["rows"]
    assert r.json["stats"]["total"] == 3
    c = client.post("/api/import/commit", json={"rows": rows}).json
    assert c["imported"] == 3
    assert c["balance"] == round(30000 - 245 - 1180.5, 2)
    # Same file again: everything is flagged duplicate and skipped.
    data = {"file": (io.BytesIO(HDFC_STYLE.encode()), "statement.csv")}
    r = client.post("/api/import/preview", data=data, content_type="multipart/form-data")
    assert r.json["stats"]["duplicates"] == 3
    assert client.post("/api/import/commit", json={"rows": rows}).json["imported"] == 0


def test_import_rejects_bad_files(client, user):
    data = {"file": (io.BytesIO(b"hello"), "photo.png")}
    assert client.post("/api/import/preview", data=data, content_type="multipart/form-data").status_code == 400
    data = {"file": (io.BytesIO(b"a,b,c\n1,2,3"), "x.csv")}
    assert client.post("/api/import/preview", data=data, content_type="multipart/form-data").status_code == 400
    big = {"file": (io.BytesIO(b"x" * (3 * 1024 * 1024)), "big.csv")}
    assert client.post("/api/import/preview", data=big, content_type="multipart/form-data").status_code == 413


def test_sample_file_parses():
    with open(SAMPLE, encoding="utf-8") as f:
        rows, _ = parse_statement(f.read())
    assert len(rows) >= 30
