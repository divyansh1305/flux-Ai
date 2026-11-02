# Explaining Flux in an interview

## The 60-second pitch (8–10 lines)

1. **Problem:** UPI made paying effortless. Young Indians' money is now spread across GPay, PhonePe, bank SMS and statements, and no app gives one number they can trust.
2. **What I built:** Flux, an automatic money tracker that logs every UPI and bank payment by itself and keeps a ledger that is actually *correct*.
3. **Capture:** an Android companion app I wrote in Kotlin reads payment notifications, filters on the phone, and sends only completed payments. iPhone users forward bank SMS through a Shortcuts automation.
4. **Parsing:** I extracted the parsing into an open-source library, `upi-parse`. On 38 messages from 9 banks it had never seen, it scored 96.6% on direction and 100% on amount.
5. **Correctness:** the same payment arrives up to four ways (Scan & Pay, SMS, notification, statement). My ledger dedupes by UPI reference, or by amount ± 1 day from a *different channel*. It also reconciles against the "Avl Bal" the bank itself reports.
6. **The useful number:** safe-to-spend today = available − bills due (auto-detected) − goal plan, divided by days left.
7. **Learning:** when a user fixes a category, Flux learns the merchant, re-files past entries and reports its *measured* accuracy from those corrections.
8. **No licences needed:** payments open the user's own UPI app through NPCI intent links, and investing goes through Zerodha Kite Publisher, so Flux never touches money.
9. **Production:** request IDs, JSON logs, Prometheus metrics, Docker, gunicorn. A load test ran at 228 req/s with p95 of 116 ms and zero errors on 2 vCPUs, and it caught three real bugs.
10. **Quality:** 162 tests in CI, including a regression test for every bug I found.

## Architecture (draw this)

```
Android app (NotificationListener) ─┐  iPhone Shortcut ─┐  Browser
         on-device filter            │                   │  session + CSRF
                                     ▼                   ▼
                 /api/ingest/*  bearer token (SHA-256 stored, per-token rate limit)
                                     │
                         upi-parse (open-source)
                                     │
        dedupe (UTR → exact; amount±1d + different origin → fuzzy)
                                     │
                 ledger (paise) ── balance snapshot ── reconcile vs bank
                                     │
         insights: safe-to-spend · recurring bills · cashback · accuracy
                                     │
                    SQLite WAL ── /metrics ── JSON logs with request id
```

## Questions you will get, and strong answers

**"How do you avoid counting a payment twice?"**
Every source is mapped to an *origin* (which app or channel saw it). If two records share a UPI reference, they are the same payment. Without a reference, records with the same kind and amount within ±1 day count as one *only if* they came from different origins. Two rules came from real failures:
- Two ₹20 chai payments seen by the same app are two payments, because the phone's notification timestamp goes into the dedupe key.
- ₹100 on GPay and ₹100 on PhonePe are two payments, because a single payment never appears in two UPI apps.

The load test found that second bug: the metrics showed 5 "duplicates" that weren't.

**"How do you know your balance is right?"**
Bank SMS and notifications usually include "Avl Bal". I store that as a snapshot linked to the transaction. Reconciliation compares Flux's balance with the latest bank balance and flags drift above ₹1. That means a payment was missed (for example cash, or a disabled notification), and the user is told to add it. There's also a double-entry projection (`/api/ledger`) whose trial balance must sum to zero.

**"Why notifications and not SMS on Android?"**
Google Play restricts READ_SMS to default SMS apps. Notification access is allowed when it is the core feature and there's a prominent disclosure, which is exactly what the first screen does. Filtering happens on the phone, so OTPs and chats never leave it. The token is encrypted with an Android Keystore key and excluded from backups.

**"What did the load test teach you?"** (best answer, give specifics)
1. `max_requests=2000` recycled my only gunicorn worker 15 times in 45 seconds. Each recycle dropped requests and wiped the in-memory rate limiter. With one worker, recycling is now off.
2. Ingest was rate-limited per IP. Jio and Airtel put thousands of users behind one carrier-NAT IP, so strangers would throttle each other. Limits are now per token. Failed token attempts are capped per IP, and a valid token is never blocked.
3. The dashboard ran 40 SQL queries because `balance()` was recomputed five times. I memoised it per request with a cache key that includes SQLite's `total_changes`, so any write invalidates it automatically. That brought it to 28 queries, 28% faster.

**"How accurate is the parser, honestly?"**
I built a synthetic set of 1,220 messages and a hand-written held-out set of 38 messages from 9 banks I never developed against. The held-out first run is the only true out-of-sample number: 96.6% direction, 100% amount, 86.2% category. After fixing what it revealed, both sets became regression tests, not accuracy claims. In production, accuracy is measured from user corrections, and users can opt in to export *masked* samples. Masking removes names, phone numbers, account numbers and references, and a test checks that masked text still parses identically.

**"Why SQLite? How would you scale?"**
SQLite in WAL mode handles this load on one box, and it keeps the system simple. The path to scale:
- Move to Postgres; queries are already parameterised.
- Move the rate limiter and metrics to Redis or a Prometheus multiprocess setup.
- Run more gunicorn workers behind a load balancer.
- Turn ingest into a queue (SQS or Kafka) so parsing is async and retries are idempotent. Dedupe is already idempotent.

**"Can Flux move money?"**
No, by design. UPI initiation needs NPCI TPAP approval, so Flux uses `upi://pay` intent links to open the user's own UPI app. Stock orders go through Kite Publisher, where the user confirms in Zerodha's window. That fits SEBI's 2026 algo rules.

**"How does voice work?"**
- Web Speech API → text → a rule parser in English, Hindi and Hinglish, taking about 1 ms.
- If the rules fail, a Gemini fallback runs, and its JSON is validated against the same whitelist of actions.
- Amounts over ₹50,000 need a spoken "yes".
- New intents: "aaj kitna kharch kar sakta hoon?" (safe-to-spend) and "what bills are coming up?".

**"Hardest bugs?"**
1. My first version decoded Google login tokens without verifying the signature. I now verify signature, expiry and audience.
2. The server ran in UTC, so evening payments in IST were dated "yesterday". All dates now come from `clock.today()` in Asia/Kolkata.
3. The cross-app dedupe and NAT rate-limit bugs above.

**"What did you learn?"**
Correctness is the product. A tracker that's 95% right gets abandoned the first time the balance is wrong, so I invested in dedupe, reconciliation and measuring accuracy instead of adding more features.

## Numbers to remember

- 162 tests passing
- 228 req/s, p95 116 ms, 0 errors (500 users, 60 s, 2 vCPU)
- 40 → 28 queries on the dashboard
- Parser on unseen banks: 96.6% direction, 100% amount, 86.2% category, 91.7% UTR
- 3 production bugs found by load testing
- Android app: about 440 lines of Kotlin, 0 third-party libraries
