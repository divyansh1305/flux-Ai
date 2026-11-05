"""Run from the project folder, with the app running on port 5066 and its output in qa-server.log:
    ADMIN_EMAILS=qa@kitna.test DATABASE_PATH=/tmp/qa.db PORT=5066 python run.py > qa-server.log 2>&1 &
    mkdir -p qa-shots && python scripts/qa/qa.py && python scripts/qa/e2e.py

Kitna UI/UX check: every screen, phone + laptop, light + dark.
Per screen: page errors, console errors, failed requests, sideways overflow, small tap targets, low-contrast text.
Screenshots go to /home/claude/qa/shots/."""
import datetime as dt
import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

B = "http://localhost:5066"
LOG = "qa-server.log"
S = "qa-shots/"
today = dt.date.today()
d = lambda n: (today - dt.timedelta(days=n)).isoformat()  # noqa: E731

CHECK_JS = r"""
() => {
  const out = {overflow: [], small: [], contrast: []};
  const W = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth > W + 1) {
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.width && r.right > W + 1 && getComputedStyle(el).position !== 'fixed') {
        let p = el.parentElement, clipped = false;
        while (p) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'hidden' || o === 'scroll') { clipped = true; break; } p = p.parentElement; }
        if (!clipped) out.overflow.push((el.className || el.tagName) + ' →' + Math.round(r.right - W) + 'px');
      }
    }
    out.overflow = [...new Set(out.overflow)].slice(0, 6);
  }
  const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  for (const el of document.querySelectorAll('button, a[href], input:not([type=hidden]), select, [role=button]')) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    if (el.type === 'checkbox' || el.type === 'radio') continue;
    const inText = el.tagName === 'A' && getComputedStyle(el).display === 'inline';
    if (!inText && (r.height < 32 || r.width < 32)) out.small.push((el.getAttribute('aria-label') || el.textContent || el.className).trim().slice(0, 30) + ` ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  out.small = [...new Set(out.small)].slice(0, 8);
  const lum = (c) => { const m = c.match(/[\d.]+/g); if (!m) return null; const [r,g,b] = m.slice(0,3).map(Number).map(v => { v/=255; return v <= .03928 ? v/12.92 : Math.pow((v+.055)/1.055, 2.4); }); return .2126*r + .7152*g + .0722*b; };
  const alpha = (c) => { const m = c.match(/[\d.]+/g); return m && m.length > 3 ? Number(m[3]) : 1; };
  const bgOf = (el) => { while (el) { const b = getComputedStyle(el).backgroundColor; if (b && alpha(b) > 0.5) return b; el = el.parentElement; } return getComputedStyle(document.body).backgroundColor; };
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.nodeValue.trim().length > 1);
    if (!own) continue;
    const cs = getComputedStyle(el);
    if (el.closest('svg')) continue;
    const fg = lum(cs.color), bg = lum(bgOf(el));
    if (fg == null || bg == null) continue;
    const ratio = (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05) * (alpha(cs.color) < 1 ? alpha(cs.color) : 1);
    const big = parseFloat(cs.fontSize) >= 24 || (parseFloat(cs.fontSize) >= 18.6 && Number(cs.fontWeight) >= 700);
    if (ratio < (big ? 3 : 4.5)) out.contrast.push(el.textContent.trim().slice(0, 28) + ` ${ratio.toFixed(2)}`);
  }
  out.contrast = [...new Set(out.contrast)].slice(0, 8);
  return out;
}
"""


def main():
    results = {}
    with sync_playwright() as p:
        br = p.chromium.launch()

        def session(scheme, mobile, email, name):
            ctx = br.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1280, "height": 860},
                                 device_scale_factor=2 if mobile else 1, is_mobile=mobile, color_scheme=scheme)
            pg = ctx.new_page()
            pg.goto(B + "/login")
            api = lambda m, pth, b=None: pg.evaluate("""async ([m,p,b])=>{const t=(document.cookie.match(/flux_csrf=([^;]+)/)||[])[1]||"";
              const r=await fetch(p,{method:m,headers:{"Content-Type":"application/json","X-CSRF-Token":decodeURIComponent(t)},body:b?JSON.stringify(b):undefined});
              let j=null; try{j=await r.json()}catch(e){}; return [r.status,j]}""", [m, pth, b])  # noqa: E731
            api("POST", "/api/auth/otp/request", {"email": email, "name": name})
            time.sleep(0.4)
            code = re.findall(rf"code for {re.escape(email)}: (\d{{6}})", open(LOG).read())[-1]
            api("POST", "/api/auth/otp/verify", {"email": email, "code": code})
            return ctx, pg, api

        # Seed one realistic account once.
        ctx, pg, api = session("light", True, "qa@kitna.test", "Divyansh Budhiraja")
        api("PATCH", "/api/account", {"adult_confirmed": True, "income_pattern": "monthly", "pay_day": 1, "current_balance": 18500,
                                      "cushion": 2000, "onboarded": True})
        ids = {}
        for k, amt, cat, note, day in [("income", 25000, "Salary", "Acme Tech", d(5)), ("expense", 2400, "Food & Dining", "Barbeque Nation", d(1)),
                                       ("expense", 649, "Subscriptions", "Netflix", d(32)), ("expense", 649, "Subscriptions", "Netflix", d(2)),
                                       ("expense", 180, "Transport", "Uber", d(3)), ("expense", 450, "Food & Dining", "Swiggy", d(9)),
                                       ("expense", 1200, "Shopping", "Myntra", d(12)), ("expense", 300, "Food & Dining", "Zomato", d(16))]:
            ids[note] = api("POST", "/api/transactions", {"kind": k, "amount": amt, "category": cat, "note": note, "date": day})[1]["transaction"]["id"]
        api("POST", "/api/friends/split", {"transaction_id": ids["Barbeque Nation"], "people": [{"name": "Rahul Sharma", "amount": 600}, {"name": "Priya", "amount": 600}]})
        api("POST", "/api/friends", {"person": "Karan", "amount": 350, "note": "Cab", "direction": "i_owe"})
        api("POST", "/api/plans", {"kind": "spend", "title": "Friday dinner", "amount": 1500, "date": (today + dt.timedelta(days=1)).isoformat()})
        api("POST", "/api/plans", {"kind": "income", "title": "Freelance payment", "amount": 4000, "date": (today + dt.timedelta(days=6)).isoformat(), "sure": False})
        api("PUT", "/api/budgets/Food & Dining", {"limit": 4000})
        api("PUT", "/api/budgets/Shopping", {"limit": 1000})
        api("POST", "/api/goals", {"title": "New laptop", "target": 60000, "deadline": (today + dt.timedelta(days=200)).isoformat()})
        ctx.close()

        screens = ["/", "/login", "/privacy", "/app", "/app/transactions", "/app/budgets", "/app/goals", "/app/plans", "/app/friends",
                   "/app/coach", "/app/settings", "/app/import", "/app/share", "/app/privacy-center", "/app/admin", "/no-such-page"]
        for scheme in ("light", "dark"):
            for mobile in (True, False):
                ctx, pg, api = session(scheme, mobile, "qa@kitna.test", "Divyansh Budhiraja")
                errs = []
                pg.on("pageerror", lambda e: errs.append("JS: " + str(e)[:120]))
                pg.on("console", lambda m: errs.append("console: " + m.text[:120]) if m.type == "error" and "favicon" not in m.text else None)
                pg.on("response", lambda r: errs.append(f"HTTP {r.status} {r.url[len(B):][:60]}") if r.status >= 400 and "/no-such-page" not in r.url else None)
                for path in screens:
                    errs.clear()
                    pg.goto(B + path)
                    pg.wait_for_timeout(1400)
                    tag = f"{scheme}-{'phone' if mobile else 'laptop'}{path.replace('/', '_') or '_home'}"
                    if mobile:
                        pg.screenshot(path=S + tag + ".png", full_page=True)
                    r = pg.evaluate(CHECK_JS)
                    r["errors"] = list(dict.fromkeys(errs))
                    results[tag] = r
                ctx.close()

        # A new user's onboarding, phone, both themes
        for scheme in ("light", "dark"):
            ctx, pg, api = session(scheme, True, f"new-{scheme}@kitna.test", "Aman Gupta")
            pg.goto(B + "/onboarding")
            pg.wait_for_timeout(1200)
            pg.screenshot(path=S + f"{scheme}-phone_onboarding.png", full_page=True)
            results[f"{scheme}-phone_onboarding"] = pg.evaluate(CHECK_JS)
            ctx.close()
        br.close()
    json.dump(results, open("qa-results.json", "w"), indent=1)
    bad = 0
    for k, v in results.items():
        issues = {kk: vv for kk, vv in v.items() if vv}
        if issues:
            bad += 1
            print(k, json.dumps(issues, ensure_ascii=False))
    print("screens checked:", len(results), "with issues:", bad)


if __name__ == "__main__":
    sys.exit(main())
