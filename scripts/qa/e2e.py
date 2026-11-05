"""Run from the project folder, with the app running on port 5066 and its output in qa-server.log:
    ADMIN_EMAILS=qa@kitna.test DATABASE_PATH=/tmp/qa.db PORT=5066 python run.py > qa-server.log 2>&1 &
    mkdir -p qa-shots && python scripts/qa/qa.py && python scripts/qa/e2e.py

Kitna end-to-end: a new user taps through the real screens on a phone. Each step passes or fails on its own."""
import datetime as dt
import re
import time
import traceback

from playwright.sync_api import expect, sync_playwright

B = "http://localhost:5066"
LOG = "qa-server.log"
S = "qa-shots/"
EMAIL = f"user{int(time.time())}@kitna.test"
results = []


def code_for(email):
    for _ in range(20):
        found = re.findall(rf"code for {re.escape(email)}: (\d{{6}})", open(LOG).read())
        if found:
            return found[-1]
        time.sleep(0.25)
    raise RuntimeError("no sign-in code")


def main():
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                             accept_downloads=True, locale="en-IN")
        pg = ctx.new_page()
        pg.set_default_timeout(6000)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)[:150]))
        pg.on("dialog", lambda d: d.accept())

        def step(name, fn):
            errors.clear()
            try:
                fn()
                if errors:
                    raise AssertionError("JS error: " + errors[0])
                results.append((name, "PASS", ""))
            except Exception as e:  # noqa: BLE001
                results.append((name, "FAIL", f"{type(e).__name__}: {str(e)[:300]}"))
                pg.screenshot(path=S + re.sub(r"\W+", "_", name) + ".png", full_page=True)
            print(results[-1][1], name, results[-1][2][:200], flush=True)

        def toast(text):
            expect(pg.locator(".toast").filter(has_text=text).first).to_be_visible(timeout=6000)

        def api(m, path, b=None):
            return pg.evaluate("""async ([m,p,b])=>{const t=(document.cookie.match(/flux_csrf=([^;]+)/)||[])[1]||"";
              const r=await fetch(p,{method:m,headers:{"Content-Type":"application/json","X-CSRF-Token":decodeURIComponent(t)},body:b?JSON.stringify(b):undefined});
              let j=null; try{j=await r.json()}catch(e){}; return [r.status,j]}""", [m, path, b])

        # 1. Landing → sign up
        def signup():
            pg.goto(B + "/")
            expect(pg.get_by_role("heading", name=re.compile("Pehle Kitna")).first).to_be_visible()
            pg.get_by_role("link", name="Start free").click()
            pg.wait_for_url("**/login")
            pg.locator("input[type=email]").fill(EMAIL)
            pg.get_by_role("button", name=re.compile("Continue|Send code")).first.click()
            name = pg.locator("input[autocomplete=name], input[name=name], #name")
            if name.count():
                name.first.fill("Aman Gupta")
                pg.get_by_role("button", name=re.compile("Continue|Send code|Create")).first.click()
            code = code_for(EMAIL)
            boxes = pg.locator("input[inputmode=numeric]")
            expect(boxes.first).to_be_visible()
            if boxes.count() >= 6:
                for i, ch in enumerate(code):
                    boxes.nth(i).fill(ch)
            else:
                boxes.first.fill(code)
            btn = pg.get_by_role("button", name=re.compile("Verify"))
            if btn.count() and btn.first.is_enabled():
                btn.first.click()
            pg.wait_for_url(re.compile(r"/onboarding|/app"), timeout=8000)
        step("Sign up with email code", signup)

        # 2. Onboarding
        def onboarding():
            pg.wait_for_url("**/onboarding")
            expect(pg.get_by_text("Pehle Kitna, phir kharcha.")).to_be_visible()
            pg.get_by_label(re.compile("18 or older")).check()
            pg.get_by_role("button", name="Continue").click()
            expect(pg.get_by_role("heading", name=re.compile("money come in"))).to_be_visible()
            pg.screenshot(path=S + "onboarding-2.png", full_page=True)
            same = pg.get_by_role("button", name=re.compile("Same date|every month"))
            if same.count():
                same.first.click()
            bal = pg.get_by_label(re.compile("Money in your bank now"))
            if bal.count():
                bal.first.fill("15000")
            pg.get_by_role("button", name="Continue").click()
            expect(pg.get_by_role("heading", name=re.compile("payments automatically"))).to_be_visible()
            pg.screenshot(path=S + "onboarding-3.png", full_page=True)
            pg.get_by_role("button", name=re.compile("add payments myself")).click()
            pg.wait_for_url("**/app", timeout=8000)
            expect(pg.get_by_text(re.compile("Safe to spend today"))).to_be_visible()
        step("Onboarding: 18+, payday, balance, skip connect", onboarding)

        # 3. Add an expense from the bottom bar
        def add_expense():
            pg.locator(".bottom-nav a.pay").click()
            m = pg.locator(".modal")
            m.get_by_label("Amount in rupees").fill("250")
            m.get_by_label("Category").select_option("Food & Dining")
            m.locator("input[placeholder*='Lunch']").fill("Chai Point")
            m.get_by_role("button", name="Save").click()
            toast("Saved")
            expect(pg.locator(".tx-title", has_text="Chai Point").first).to_be_visible()
        step("Add expense from the + button", add_expense)

        # 4. Plan from Home
        def add_plan():
            pg.get_by_role("button", name="Add a plan").first.click()
            m = pg.locator(".modal")
            m.locator("input[placeholder='Dinner on Friday']").fill("Movie night")
            m.get_by_label("Amount in rupees").fill("800")
            m.get_by_role("button", name="Save").click()
            toast("Plan added")
            expect(pg.locator(".tx-title", has_text="Movie night").first).to_be_visible()
        step("Add a plan from Home", add_plan)

        # 5. Split from Activity, then the friend pays back by SMS
        def split():
            pg.goto(B + "/app/transactions")
            pg.locator(".tx-main.tx-edit", has_text="Chai Point").first.click()
            pg.get_by_role("button", name="Split with friends").click()
            m = pg.locator(".modal")
            m.get_by_label("Friends' names").fill("Rahul Sharma")
            expect(m.get_by_text(re.compile("Your share: ₹125"))).to_be_visible()
            m.get_by_role("button", name="Split").click()
            toast("Friends owe you ₹125")
            pg.goto(B + "/app/friends")
            expect(pg.locator(".tx-title", has_text="Rahul Sharma")).to_be_visible()
            pg.screenshot(path=S + "friends.png", full_page=True)
        step("Split a payment with a friend", split)

        def sms_pay_back():
            tok = api("POST", "/api/ingest/token")[1]["token"]
            today = (dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)).strftime("%d-%m-%y")
            sms = f"Rs.125.00 credited to your A/c XX1234 on {today} by UPI ref no 430512345678 from RAHUL SHARMA (rahul@okaxis). -Kotak Bank"
            r = pg.request.post(B + "/api/ingest/sms", data={"text": sms}, headers={"Authorization": f"Bearer {tok}"})
            assert r.ok, r.text()
            pg.goto(B + "/app/friends")
            expect(pg.get_by_text("All square")).to_be_visible()
        step("Friend's UPI SMS ticks them off automatically", sms_pay_back)

        # 6. Budgets and goals
        def budget():
            pg.goto(B + "/app/budgets")
            pg.get_by_role("button", name="New budget").click()
            m = pg.locator(".modal")
            m.get_by_label("Category").select_option("Food & Dining")
            m.locator("input[type=number]").first.fill("3000")
            m.get_by_role("button", name="Save").click()
            expect(pg.get_by_text("Food & Dining").first).to_be_visible()
            expect(pg.get_by_text(re.compile("of ₹3,000"))).to_be_visible()
        step("Set a monthly budget", budget)

        def goal():
            pg.goto(B + "/app/goals")
            pg.get_by_role("button", name="New goal").click()
            m = pg.locator(".modal")
            m.locator("input").first.fill("Goa trip")
            m.locator("input[type=number]").first.fill("12000")
            m.get_by_role("button", name=re.compile("Create|Save")).click()
            expect(pg.get_by_text("Goa trip").first).to_be_visible()
            pg.get_by_role("button", name="Add money").first.click()
            m = pg.locator(".modal")
            m.locator("input[type=number]").first.fill("500")
            m.get_by_role("button", name=re.compile("Set aside|Save|Add")).last.click()
            expect(pg.get_by_text(re.compile("₹500")).first).to_be_visible()
        step("Create a goal and set money aside", goal)

        # 7. Imports
        def csv_import():
            pg.goto(B + "/app/import")
            pg.set_input_files("#file", "flux/static/sample_statement.csv")
            go = pg.get_by_role("button", name=re.compile(r"Import \d+ transactions"))
            expect(go).to_be_visible(timeout=10000)
            go.click()
            pg.wait_for_url("**/app", timeout=10000)
        step("Import a CSV bank statement", csv_import)

        def pdf_import():
            pg.goto(B + "/app/import")
            pg.set_input_files("#file", "scripts/qa/locked-statement.pdf")
            expect(pg.get_by_text("This PDF has a password")).to_be_visible(timeout=10000)
            pg.locator("input[type=password]").fill("wrong")
            pg.get_by_role("button", name="Open statement").click()
            expect(pg.get_by_text("That password didn't work")).to_be_visible(timeout=10000)
            pg.locator("input[type=password]").fill("DIVY0513")
            pg.get_by_role("button", name="Open statement").click()
            expect(pg.get_by_role("button", name=re.compile(r"Import \d+ transaction"))).to_be_visible(timeout=10000)
        step("Password-protected PDF statement", pdf_import)

        def share_sms():
            pg.goto(B + "/app/share")
            ta = pg.locator("textarea").first
            ta.fill("Rs.340.00 debited from A/c XX1234 on 05-11-26 to VPA rapido@ybl (UPI Ref No 430599887766). -HDFC Bank")
            pg.get_by_role("button", name=re.compile("Read|Find|Check|Preview|Add")).first.click()
            expect(pg.get_by_text(re.compile("Rapido", re.I)).first).to_be_visible(timeout=8000)
        step("Paste a bank SMS", share_sms)

        # 8. Ask
        def ask():
            pg.goto(B + "/app/coach")
            box = pg.get_by_placeholder(re.compile("Ask anything"))
            box.fill("aaj kitna safe hai")
            box.press("Enter")
            expect(pg.get_by_text(re.compile(r"₹[\d,]+")).last).to_be_visible(timeout=10000)
        step("Ask Kitna a question", ask)

        # 9. Settings: Hinglish, UPI ID, reminder types, bell
        def hinglish():
            pg.goto(B + "/app/settings")
            with pg.expect_navigation():
                pg.get_by_role("button", name="Hinglish").click()
            pg.goto(B + "/app")
            expect(pg.get_by_text(re.compile("Aaj safe kharcha"))).to_be_visible(timeout=8000)
            expect(pg.locator(".bottom-nav").get_by_text("Dost")).to_be_visible()
            pg.screenshot(path=S + "hinglish-home.png")
            pg.goto(B + "/app/settings")
            with pg.expect_navigation():
                pg.get_by_role("button", name="English").click()
            pg.goto(B + "/app")
            expect(pg.get_by_text("Safe to spend today", exact=False).first).to_be_visible()
        step("Switch to Hinglish and back", hinglish)

        def upi_and_reminders():
            pg.goto(B + "/app/settings")
            pg.get_by_label(re.compile("UPI ID")).fill("aman@okicici")
            pg.locator("#upi").get_by_role("button", name="Save").click()
            toast("UPI ID saved")
            box = pg.locator("#reminders").get_by_label(re.compile("Morning number"))
            box.uncheck()
            toast("Saved")
            assert "morning" not in api("GET", "/api/reminders")[1]["kinds"]
        step("Save UPI ID and turn off one reminder", upi_and_reminders)

        def bell():
            pg.goto(B + "/app")
            pg.locator("a.bell").click()
            expect(pg.locator(".modal").get_by_role("heading", name="Reminders")).to_be_visible()
            pg.keyboard.press("Escape")
        step("Open the reminders inbox", bell)

        # 10. Your data
        def export():
            pg.goto(B + "/app/settings")
            with pg.expect_download() as dl:
                pg.get_by_role("button", name="Download my data").click()
            path = dl.value.path()
            import json

            data = json.load(open(path))
            assert data["friends"] and data["transactions"], "export missing data"
        step("Download my data", export)

        def delete():
            pg.goto(B + "/app/settings")
            pg.get_by_role("button", name="Delete account").click()
            m = pg.locator(".modal")
            m.locator("input").fill("DELETE")
            m.get_by_role("button", name="Delete forever").click()
            pg.wait_for_url(B + "/", timeout=8000)
            assert api("GET", "/api/auth/me")[1].get("user") is None
        step("Delete account", delete)
        br.close()
    print("\n%d passed, %d failed" % (sum(r[1] == "PASS" for r in results), sum(r[1] == "FAIL" for r in results)))


if __name__ == "__main__":
    main()
