# Flux: the money tracker that's actually right

**Flux logs every UPI and bank payment automatically and keeps a ledger you can trust.** It shows how much you can safely spend today, whether your numbers match your bank's, and how much cashback is really worth to you. It also helps you save and invest without ever touching your money. Everything works by voice, in English, Hindi or Hinglish.

🛠 Go-live steps: [`docs/SETUP.md`](docs/SETUP.md) · 📄 Interview guide: [`docs/INTERVIEW.md`](docs/INTERVIEW.md) · 🚀 Launch plan: [`docs/LAUNCH.md`](docs/LAUNCH.md) · 📦 Open-source parser: [`packages/upi_parse`](packages/upi_parse) · 🤖 Android app: [`android/`](android)

> **Safe to spend today: ₹412.** ₹9,840 available · ₹3,200 bills before month-end · ₹1,500 goal plan · 🏦 Bank says ₹9,840 ✓ in sync

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
| "Is this number even right?" | **One ledger, no double counting.** The same payment seen by Scan & Pay, the bank SMS, the notification and the statement is matched (by UPI reference, or amount ± 1 day from a different channel) and stored once. The bank's own "Avl Bal" is captured to **reconcile** your Flux balance against your real one. |
| "Can I afford this?" | **Safe to spend today** = (available − bills due before month-end − goal plan) ÷ days left. Recurring bills are detected automatically. Scanning a UPI QR shows the impact *before* your UPI app opens. |
| "Is cashback helping me?" | **Cashback vs auto-save** compares cashback received with what round-up auto-save actually put away. |
| "How do I start saving and investing?" | **Auto-save** rounds up each expense into a goal (only if you have the balance). Goal money can buy index ETFs in **your own Zerodha account** via Kite Publisher. |
| "Did Flux file it correctly?" | **You correct it, Flux learns.** Tap a transaction to fix its category and tick "always use this". Flux re-files earlier entries, applies the rule to future payments, and shows its **measured accuracy** from your corrections. |

## Numbers (measured, not claimed)

| What | Result | How |
|---|---|---|
| Parser accuracy on unseen bank formats | **96.6% direction, 100% amount, 86.2% category, 91.7% UTR** (first run, 38 messages from 9 banks never used in development) | `packages/upi_parse/benchmarks/evaluate.py` |
| Load test (2 vCPU, 1 gunicorn worker × 8 threads, load generator on the same box) | **228 req/s, p95 116 ms, p99 171 ms, 0 errors** over 60 s · 500 users with 6 months of history | `scripts/loadtest.py` → [`docs/loadtest-results.json`](docs/loadtest-results.json) |
| Dashboard query count | **40 → 28 SQL queries** (6.8 → 4.9 ms) after per-request memoisation keyed on SQLite `total_changes` | profiled with cProfile + sqlite trace |
| Tests | **162 passing** (app + library), on every push in CI | `pytest -q` |

The load test also caught three production bugs before any user did: worker recycling every few seconds at `max_requests=2000`, per-IP rate limits that would make Jio/Airtel users behind carrier NAT throttle each other, and two different UPI apps' identical payments being merged as duplicates.

## Features

- 🤖 **Android companion app** (Kotlin, no third-party libraries): NotificationListenerService, on-device filtering (OTPs and chats never leave the phone), Keystore-encrypted token, offline retry queue, and the Play-policy prominent disclosure. See [`android/README.md`](android/README.md).
- 🍎 **iPhone automation:** a Shortcuts "Message" automation posts bank SMS to `/api/ingest/sms` with a revocable bearer token (stored as a SHA-256 hash).
- 🧾 **Ledger integrity:** cross-source dedupe, bank-balance reconciliation with drift alerts, a double-entry trial balance at `/api/ledger`, and integer paise everywhere.
- 🔮 **Safe-to-spend, recurring bills, month-end forecast, Money Health Score.**
- 🧠 **Learns from corrections:** merchant rules, re-filing of past entries, measured categorisation accuracy, and an opt-in masked sample export for improving the parser.
- 📷 **Scan & Pay:** NPCI UPI-linking-spec QR parsing, MCC → category, pre-spend check, then it opens your UPI app pre-filled.
- 📈 **Invest from goals:** curated index and gold ETFs via Zerodha Kite Publisher, holdings and P&L, and practice mode without a key.
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
  api/             auth, money, pay, invest, statement, ingest, voice
packages/upi_parse/  pip-installable parser library + benchmarks (MIT)
android/         Flux Companion (Kotlin)
scripts/loadtest.py
tests/           pytest suite
```

## Regulatory design (why Flux never touches money)

- **Payments:** initiating UPI payments needs NPCI approval as a Third-Party App Provider. Flux opens the user's own UPI app with `upi://pay?…` intent links, so the PIN and the money never pass through Flux.
- **Investing:** SEBI's retail algo framework (fully in force from April 2026) requires static IPs and empanelment for API orders. Kite Publisher opens the order in Zerodha's own window for the user to confirm.
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

`render.yaml` deploys to Render with a persistent disk. Set `EMAIL_SENDER` and `EMAIL_PASSWORD`, and optionally `GEMINI_API_KEY`, `GOOGLE_CLIENT_ID`, `KITE_API_KEY` and `METRICS_TOKEN`. The full checklist is in [`docs/LAUNCH.md`](docs/LAUNCH.md).

## Roadmap

- Account Aggregator sync via a licensed FIU partner.
- Postgres plus a Redis rate limiter, then more gunicorn workers.
- Publish `upi-parse` to PyPI, with accuracy on real consented samples.
- UPI payment-result callback in the Android app (intent result) to close the Scan & Pay loop automatically.

---

*Flux is a budgeting tool, not financial advice.*
