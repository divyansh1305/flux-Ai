"""Only real, working features are shown; iPhone one-link auto-logging."""


def test_invest_is_gone_and_pay_is_back(app, client, user):
    assert client.get("/app/invest").status_code == 404
    assert client.get("/app/pay").status_code == 200
    assert client.get("/api/pay/pending").status_code == 200


def test_iphone_one_link_accepts_raw_form_and_json(app, client, user):
    t = client.post("/api/ingest/token").json
    assert t["iphone_url"].endswith("/api/ingest/sms/" + t["token"])
    path = "/api/ingest/sms/" + t["token"]
    phone = app.test_client()
    # Shortcuts "Request Body: File" → raw text body
    r1 = phone.post(path, data="Sent Rs.100.00 From HDFC Bank A/C *1234 To RAHUL KUMAR On 03/11/26 Ref 630712345678",
                    content_type="text/plain").json
    assert r1["logged"] and r1["amount"] == 100
    r2 = phone.post(path, data={"text": "Rs.250.00 debited from A/c XX1234 on 03-11-26 to VPA swiggy@icici UPI Ref 512345678901"}).json
    assert r2["logged"] and r2["category"] == "Food & Dining"
    r3 = phone.post(path, json={"text": "Your OTP is 445566"}).json
    assert not r3["logged"]
    assert phone.post("/api/ingest/sms/flx_wrong", data="Sent Rs.5").status_code == 401
