# Launch plan: from code to real users

The goal is **50 weekly active users whose balance stays in sync with their bank**. That's the number that proves the product works, and it's what you quote in interviews.

## 1. Deploy (about 1 hour)

- [ ] **Rotate the old Gemini keys** that were in the original project's code and `.env`. Create a new key at aistudio.google.com/apikey.
- [ ] Push `flux-v2` to a **new private GitHub repo**. Check that `.env`, `*.db` and `statement.csv` are *not* in it (`git status` before the first commit).
- [ ] Render → New → Blueprint → pick the repo. `render.yaml` creates the service, the disk, `SECRET_KEY` and `METRICS_TOKEN`.
- [ ] Set `EMAIL_SENDER` and `EMAIL_PASSWORD` (a Gmail App Password), `GEMINI_API_KEY`, and optionally `GOOGLE_CLIENT_ID`.
- [ ] Open `https://<app>.onrender.com/readyz` and check it shows `{"ok": true}`.
- [ ] Sign up yourself, then create a token in Settings → Automatic tracking.
- [ ] Free Render instances sleep after 15 minutes idle, and the first request then takes about 30 s. Before launch, use the Starter plan (about $7/month) or point an uptime pinger at `/healthz`.

## 2. Phones (about 1 hour)

- [ ] **Android:** open `android/` in Android Studio, then Run on your phone. Paste the server URL and token, then turn on Notification access. Make a ₹1 UPI payment and watch it appear.
- [ ] **iPhone:** follow the Shortcuts steps shown in Settings (on the live site, not localhost).
- [ ] Check reconciliation: after a bank SMS with "Avl Bal" arrives, the dashboard should say "🏦 Bank says … ✓ in sync". If it shows drift, add the missing transaction and confirm it turns green.

## 3. Watch it (5 minutes a day)

- `/metrics` with `Authorization: Bearer $METRICS_TOKEN` (Grafana Cloud's free tier can scrape it). Watch:
  - `flux_ingest_total{result="logged"}`: payments captured automatically
  - `flux_ingest_total{result="skipped"}`: high values mean a bank format the parser doesn't know, so check the masked samples
  - `flux_http_request_duration_seconds`: p95 should stay under 300 ms
- Render logs are JSON. Search by `request_id` when a user reports a problem; the ID is in every response header.

## 4. First 50 users (2–4 weeks)

Who: classmates, hostel groups and college clubs. These are people who pay by UPI every day and have never kept a budget.

- [ ] Recruit 10 friends first. Sit with each one during setup, and write down every confusing step and fix it the same day.
- [ ] Ask each of them to turn on **"Help improve accuracy"** and send you their masked samples file after 2 weeks. Run `python packages/upi_parse/benchmarks/evaluate.py samples.jsonl`. This gives a real-world accuracy number on consented data, which very few student projects have.
- [ ] Post in college WhatsApp groups with a 30-second screen recording of a GPay payment appearing in Kitna by itself.
- [ ] Track these weekly in a spreadsheet:
  - signups
  - weekly active users
  - % of users with automatic logging on
  - % of users "in sync" with their bank
  - median categorisation accuracy (Coach page)
  - D7 and D30 retention

## 5. Publish the library

- [ ] `cd packages/upi_parse && python -m build && twine upload dist/*` to put `upi-parse` on PyPI.
- [ ] Add each bank format a user reports as a held-out test case before fixing it. Re-run the benchmark and update the accuracy table honestly.

## 6. Google Play (optional, after the 10-friend test)

- [ ] A Play Console account costs $25, one-time.
- [ ] Data safety form: financial info (purchase history) is collected, encrypted in transit and deletable. Link the privacy policy at `https://<app>/privacy`.
- [ ] Notification-access declaration: it is the core feature, with a prominent disclosure on the first screen (already built).
- [ ] An internal testing track is enough for friends. Production review takes days, so start early.

## What to say in interviews once this is done

> "Kitna has N weekly users. X% of them have automatic logging on, and Y% stay in sync with their bank balance. On Z real consented messages, the parser gets A% of categories right. That's measured from user corrections, not a test set I wrote."

Fill in N, X, Y, Z and A from the spreadsheet. **Real numbers beat any feature list.**
