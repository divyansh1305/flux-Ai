# Flux: the money tracker that's actually right

**Flux logs every UPI and bank payment automatically and keeps a ledger you can trust.** It tells you how much you can safely spend today, built from *your* payday, plans and safety cushion, checks itself against your bank, and catches real problems: failed payments whose money hasn't come back, double charges and subscription price rises. It never moves money, never offers loans and never sells data. For ages 18+.

🛠 Deploy and update: [`docs/DEPLOY.md`](docs/DEPLOY.md) · 📄 Interview guide: [`docs/INTERVIEW.md`](docs/INTERVIEW.md) · 🚀 Launch plan: [`docs/LAUNCH.md`](docs/LAUNCH.md) · 📦 Open-source parser: [`packages/upi_parse`](packages/upi_parse) · 🤖 Android app: [`android/`](android)

> **Safe to spend today: ₹404.** ₹13,502 you have − ₹2,000 Friday dinner plan − ₹1,000 cushion, ÷ 26 days until payday on 1 Dec · watching ₹850 failed payment to Myntra (refund due by 10 Nov)

---

## The problem

UPI made spending effortless, but nothing made *knowing where you stand* effortless.

- In an IIIT Delhi study of UPI users, **74%** said UPI made them spend more, and **~60%** had gone over budget because of it ([Dev, Gupta & Kumar, 2024](https://arxiv.org/abs/2401.09937)).
- Money is spread across GPay, PhonePe, bank SMS and statements, and none of them agree on a single number.
- Budgeting apps die because manual entry dies. When they do auto-import, they double-count: the same ₹347 shows up as a UPI payment, a bank SMS *and* a statement row.
- Cashback is marketed as saving, but it rewards spending more.

**Who it's for:** students and first-job earners (18–28) who pay mostly by UPI.

## What Flux does

| Question | How Flux answers it |
|---|---|
| "Where did my money go?" | **Logs itself.** The Android companion app reads payment notifications (GPay, PhonePe, Paytm, bank apps). iPhone users forward bank SMS with a Shortcuts automation. Statements import from CSV. All of it goes through the open-source `upi-parse` library. |
| "Is this number even right?" | **One ledger, no double counting.** The same payment seen in a UPI app notification, the bank SMS, Gmail and the statement is matched (by UPI reference, or amount ± 1 day from a different channel) and stored once. The bank's own "Avl Bal" is captured to **reconcile** your Flux balance against your real one. |
| "What can I spend today?" | **Personal safe-to-spend** = (money you have + money you're *sure* is coming − bills due − your plans − goal top-ups − your safety cushion) ÷ days until *your* next payday (or month end if income varies). Tap it to see every line. Plans like "Dinner Friday ₹2,000" are kept aside, and a plan paid today isn't counted twice. |
| "Is anything wrong?" | **Money checks:** a failed payment is watched until the refund arrives, with the RBI deadlines (T+1 transfer, T+5 merchant, ₹100/day after); double charges (same merchant, amount and day, different bank refs); subscription price rises. Each can be dismissed for good. |
| "What do you have about me?" | **What Flux knows:** every source and record type counted, export, delete (which also revokes Gmail). 18+ only, as India's DPDP rules require for behavioural tracking. |
| "Did Flux file it correctly?" | **You correct it, Flux learns.** Tap a transaction to fix its category and tick "always use this". Flux re-files earlier entries, applies the rule to future payments, and shows its **measured accuracy** from your corrections. |

## Numbers (measured, not claimed)

| What | Result | How |
|---|---|---|
| Parser accuracy on unseen bank formats | **96.6% direction, 100% amount, 86.2% category, 91.7% UTR** (first run, 38 messages from 9 banks never used in development) | `packages/upi_parse/benchmarks/evaluate.py` |
| Load test (2 vCPU, 1 gunicorn worker × 8 threads, load generator on the same box) | **228 req/s, p95 116 ms, p99 171 ms, 0 errors** over 60 s · 500 users with 6 months of history | `scripts/loadtest.py` → [`docs/loadtest-results.json`](docs/loadtest-results.json) |
| Dashboard query count | **40 → 28 SQL queries** (6.8 → 4.9 ms) after per-request memoisation keyed on SQLite `total_changes` | profiled with cProfile + sqlite trace |
| Tests | **180 passing** (app) + library tests, on every push in CI | `pytest -q` |

The load test also caught three production bugs before any user did: worker recycling every few seconds at `max_requests=2000`, per-IP rate limits that would make Jio/Airtel users behind carrier NAT throttle each other, and two different UPI apps' identical payments being merged as duplicates.

## Features

- 🤖 **Android companion app** (Kotlin, no third-party libraries): NotificationListenerService, on-device filtering (OTPs and chats never leave the phone), Keystore-encrypted token, offline retry queue, and the Play-policy prominent disclosure. See [`android/README.md`](android/README.md).
- 📧 **Gmail connect:** read-only OAuth, Fernet-encrypted refresh token, last 30 days imported at once, email bodies never stored, dead links detected and shown as "Reconnect".
- 🍎 **iPhone automation:** a Shortcuts "Message" automation posts bank SMS to `/api/ingest/sms` with a revocable bearer token (stored as a SHA-256 hash).
- 📦 **Android APK built in CI:** `.github/workflows/android.yml` builds the companion app and publishes it as a download; the website links it with one tap through a `fluxapp://connect` deep link that only accepts the official server.
- 🧾 **Ledger integrity:** cross-source dedupe, bank-balance reconciliation with drift alerts, a double-entry trial balance at `/api/ledger`, and integer paise everywhere.
- 🔮 **Personal safe-to-spend, plans, safety cushion, recurring bills, month-end forecast, money checks.**
- 📊 **Product analytics without personal data:** an `events` table records only *what happened* ("plan_added", "auto_payment: sms"), validated against a whitelist so no amounts, merchants or text can get in. A nightly job rolls it into `daily_stats`, and a private numbers page (`/app/admin`, for `ADMIN_EMAILS`) shows the setup funnel, day-1/7/30 return rates, read rate per source, money-check usefulness and ₹ kept. Events are deleted with the account and after 13 months.
- ⚡ **Instant screens:** a service worker serves the app shell from the phone, screens draw from the last data seen and refresh in the background, files are content-hashed and cached for a year, and responses are gzipped. On a simulated 300 ms mobile link, opening a screen went from 1.15–1.50 s to about 0.1 s.
- 🧠 **Learns from corrections:** merchant rules, re-filing of past entries, measured categorisation accuracy, and an opt-in masked sample export for improving the parser.
- 🎙️ **Voice:** "spent 340 on Zomato", "aaj kitna kharch kar sakta hoon?", "what bills are coming up?". Rule parser first, Gemini fallback validated against a whitelist.
- 📄 Statement import, budgets, goals, AI coach, monthly PDF report, CSV/PDF export, full data export and account deletion. Installable PWA.

## Architecture

```
 Android companion ─┐   iPhone Shortcut ─┐   Browser (vanilla JS, voice, QR)
  notification text │     bank SMS text  │        │ cookie session + CSRF
                    ▼                    ▼        ▼
            POST /api/ingest/*  (bearer token, per-token rate limit)
                    │
             upi-parse (open-source library: SMS · notifications · narrations · UPI QR · masking)
                    │
   ledger.find_duplicate ──► finance.add_transaction ──► balance snapshot ──► reconcile
                    │                     │
             merchant rules        insights: safe-to-spend · recurring · cashback · accuracy
                    ▼
   SQLite (WAL, paise integers, PRAGMA user_version migrations)
   Observability: X-Request-ID · JSON access logs · Prometheus /metrics · /readyz
```

```
flux/            Flask app (factory + blueprints)
  finance.py       the only place money maths happens; per-request memoised aggregates
  ledger.py        dedupe, balance snapshots, reconciliation, double-entry journal
  insights.py      safe-to-spend, recurring detection, cashback report
  observability.py request ids, JSON logs, Prometheus metrics
  security.py      auth, CSRF, rate limiting (per IP or per token), CSP, validation
  api/             auth, money, plans, statement, ingest, gmail, voice
packages/upi_parse/  pip-installable parser library + benchmarks (MIT)
android/         Flux Companion (Kotlin)
scripts/loadtest.py
tests/           pytest suite
```

## Regulatory design (why Flux never touches money)

- **Payments and investing:** initiating UPI payments needs NPCI approval as a Third-Party App Provider, and API stock orders need SEBI empanelment. Flux does neither: it only reads, so the PIN and the money never pass through Flux.
- **Personal data (DPDP Act and Rules 2025):** plain-language notice, export and delete, purpose-limited use, and 18+ only because tracking spending habits counts as behavioural monitoring, which is restricted for under-18s.
- **Bank data:** notifications, SMS and CSV today, all user-initiated and consented. The production path for direct bank sync is the RBI Account Aggregator framework through a licensed FIU partner (for example Setu).
- **Google Play:** SMS permissions are restricted, so the Android app uses notification access with a prominent disclosure and consent screen.

## Security

- Email OTP (hashed, 10-minute expiry, 5 attempts) and verified Google Sign-In. Session rotation; HttpOnly, SameSite and Secure cookies.
- CSRF on every cookie-authenticated write. Strict CSP. HSTS, nosniff and frame-ancestors none.
- Ingest tokens: 256-bit, stored hashed, revocable, and rate-limited **per token**. Failed-token attempts are capped per IP, and a valid token is never blocked by someone else's spraying.
- Every query is scoped to the signed-in user (tested with two users). Output uses `textContent` only. CSV formula-injection protection.
- AI output can only trigger whitelisted actions.
- Android: the token is encrypted with an Android Keystore AES-GCM key, backups are excluded, and cleartext traffic is off.

## Run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # optional keys
python run.py                   # http://127.0.0.1:5000 – sign-in code prints in the terminal
pytest -q                       # 162 tests
```

Load test: see the header of `scripts/loadtest.py`. Docker: `docker build -t flux . && docker run -p 8000:8000 -e SECRET_KEY=… -v flux-data:/data flux`.

## Deploy

`render.yaml` deploys to Render with a persistent disk. Set `EMAIL_SENDER` and `EMAIL_PASSWORD`, and optionally `GEMINI_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `METRICS_TOKEN`. The full checklist is in [`docs/LAUNCH.md`](docs/LAUNCH.md).

## Roadmap

- Account Aggregator sync via a licensed FIU partner.
- Postgres plus a Redis rate limiter, then more gunicorn workers.
- Publish `upi-parse` to PyPI, with accuracy on real consented samples.

---

*Flux is a budgeting tool, not financial advice.*
