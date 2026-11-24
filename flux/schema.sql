-- Kitna database schema (SQLite).
-- All money is stored as INTEGER paise (₹1 = 100) to avoid floating-point errors.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    onboarded       INTEGER NOT NULL DEFAULT 0,
    -- Auto-save: 'off' | 'roundup' | 'percent'
    autosave_mode   TEXT NOT NULL DEFAULT 'roundup' CHECK (autosave_mode IN ('off','roundup','percent')),
    -- roundup: round each expense up to the next multiple of this many rupees
    -- percent: save this percent of each expense
    autosave_value  INTEGER NOT NULL DEFAULT 10,
    autosave_goal_id INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    voice_lang      TEXT NOT NULL DEFAULT 'en-IN'
);

CREATE TABLE IF NOT EXISTS otp_codes (
    email           TEXT PRIMARY KEY,
    code_hash       TEXT NOT NULL,
    expires_at      INTEGER NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_sent_at    INTEGER NOT NULL,
    pending_name    TEXT
);

CREATE TABLE IF NOT EXISTS goals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    target          INTEGER NOT NULL CHECK (target > 0),
    deadline        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    archived        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- income: money in | expense: money out | saving: moved from balance into a goal
    -- (negative saving = withdrawn from a goal back to balance)
    kind            TEXT NOT NULL CHECK (kind IN ('income','expense','saving')),
    amount          INTEGER NOT NULL,
    category        TEXT NOT NULL,
    note            TEXT NOT NULL DEFAULT '',
    date            TEXT NOT NULL,
    goal_id         INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    parent_id       INTEGER REFERENCES transactions(id) ON DELETE CASCADE,
    source          TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','voice','import','autosave','upi','sms','invest','notification','email')),
    import_hash     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    ref             TEXT,           -- bank/UPI reference (UTR/RRN): exact key for cross-source de-duplication
    origin          TEXT,           -- finer than source: which app/channel saw it (e.g. com.phonepe.app, sms). Dedupe compares this.
    auto_category   TEXT            -- what Kitna assigned automatically; differs from `category` once the user corrects it
);

CREATE INDEX IF NOT EXISTS idx_tx_user_date ON transactions(user_id, date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_import ON transactions(user_id, import_hash) WHERE import_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tx_ref ON transactions(user_id, ref) WHERE ref IS NOT NULL;

CREATE TABLE IF NOT EXISTS budgets (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category        TEXT NOT NULL,
    monthly_limit   INTEGER NOT NULL CHECK (monthly_limit > 0),
    PRIMARY KEY (user_id, category)
);

-- Investments bought from goal savings (in the user's own Zerodha account, or practice mode).
CREATE TABLE IF NOT EXISTS investments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_id         INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    symbol          TEXT NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    price           INTEGER NOT NULL CHECK (price > 0),
    mode            TEXT NOT NULL CHECK (mode IN ('kite','practice')),
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','holding','sold','cancelled')),
    sold_price      INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_inv_user ON investments(user_id, status);

-- Personal tokens for automatic SMS logging (iPhone Shortcuts / Android forwarders).
-- Only a hash is stored; the token itself is shown to the user once.
CREATE TABLE IF NOT EXISTS ingest_tokens (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at    TEXT,
    uses            INTEGER NOT NULL DEFAULT 0
);

-- Balances the bank itself reported ("Avl Bal" in SMS / statement closing balance).
-- Used to show the real bank balance and to detect transactions Kitna missed.
CREATE TABLE IF NOT EXISTS balance_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_last4   TEXT,
    balance         INTEGER NOT NULL,
    transaction_id  INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    observed_date   TEXT NOT NULL,
    source          TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_snap_user ON balance_snapshots(user_id, id);

-- "Always put <merchant> in <category>": learned from the user's own corrections.
CREATE TABLE IF NOT EXISTS merchant_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    merchant_key    TEXT NOT NULL,
    category        TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, merchant_key)
);

-- Opt-in only: masked message text kept so the user can export labelled parser test cases.
CREATE TABLE IF NOT EXISTS parse_samples (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    transaction_id  INTEGER REFERENCES transactions(id) ON DELETE CASCADE,
    source          TEXT NOT NULL,
    masked_text     TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_samples_user ON parse_samples(user_id);

-- Gmail connect: read-only access to bank alert emails. Only the refresh token is kept (encrypted).
CREATE TABLE IF NOT EXISTS gmail_accounts (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    refresh_token   TEXT NOT NULL,          -- Fernet-encrypted with a key derived from SECRET_KEY
    connected_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_sync_at    TEXT,
    imported        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT
);

-- Which emails were already looked at, so each is read once (no email content is stored).
CREATE TABLE IF NOT EXISTS gmail_seen (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    msg_id          TEXT NOT NULL,
    PRIMARY KEY (user_id, msg_id)
);

-- Plans: money the user expects to spend (dinner on Friday) or receive (client pays on the 20th).
-- Spend plans are kept out of "safe to spend" until their day; income plans count only when marked sure.
CREATE TABLE IF NOT EXISTS plans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL DEFAULT 'spend' CHECK (kind IN ('spend','income')),
    title           TEXT NOT NULL,
    amount          INTEGER NOT NULL CHECK (amount > 0),
    date            TEXT NOT NULL,
    sure            INTEGER NOT NULL DEFAULT 1,
    done            INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_plans_user_date ON plans(user_id, date);

-- Payments the bank said failed: money may have left the account and must come back (RBI T+1 / T+5 rules).
CREATE TABLE IF NOT EXISTS refund_watch (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount          INTEGER NOT NULL,
    date            TEXT NOT NULL,
    note            TEXT NOT NULL DEFAULT '',
    ref             TEXT,
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','back','ignored')),
    fingerprint     TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, fingerprint)
);

-- Money checks the user dismissed ("not a double charge"), so they never show again.
CREATE TABLE IF NOT EXISTS dismissed_checks (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    check_key       TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, check_key)
);

-- Product events: what people DO in Kitna (never amounts, merchants or message text). Used only in totals
-- to improve the app. Deleted with the account; purged after 13 months (daily_stats keeps the totals).
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    prop            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_name_time ON events(name, created_at);
CREATE INDEX IF NOT EXISTS idx_events_user_time ON events(user_id, created_at);

-- One row per day per number (sign-ups, active users, automatic payments by source, ...). Built nightly.
CREATE TABLE IF NOT EXISTS daily_stats (
    day             TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           REAL NOT NULL,
    PRIMARY KEY (day, metric)
);

-- Which money checks a user has already been shown, so "check_found" is counted once per check.
CREATE TABLE IF NOT EXISTS seen_checks (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    check_key       TEXT NOT NULL,
    PRIMARY KEY (user_id, check_key)
);

-- Phones that turned reminders on. One row per browser; removed when the push service says it's gone (404/410).
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint        TEXT NOT NULL UNIQUE,
    p256dh          TEXT NOT NULL,
    auth            TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_ok_at      TEXT,
    fails           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_push_user ON push_subscriptions(user_id);

-- Every reminder Kitna made, so the same one is never sent twice and people without push still see it in the app.
CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    dedupe_key      TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    url             TEXT NOT NULL DEFAULT '/app',
    pushed          INTEGER NOT NULL DEFAULT 0,
    read_at         TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, dedupe_key)
);
CREATE INDEX IF NOT EXISTS idx_notif_user_time ON notifications(user_id, created_at);

-- Money between the user and friends: "they_owe" (I paid for dinner, Rahul owes ₹500) or "i_owe".
-- Closed automatically when a matching UPI payment arrives, or by hand.
CREATE TABLE IF NOT EXISTS owed (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    direction       TEXT NOT NULL DEFAULT 'they_owe' CHECK (direction IN ('they_owe','i_owe')),
    person          TEXT NOT NULL,
    amount          INTEGER NOT NULL CHECK (amount > 0),
    note            TEXT NOT NULL DEFAULT '',
    date            TEXT NOT NULL,
    transaction_id  INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    settled_at      TEXT,
    settled_tx_id   INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    suggested_tx_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_owed_user_open ON owed(user_id, settled_at);

-- What people tell us from inside the app ("Send feedback"). Their own words, kept with the account (deleted with it).
CREATE TABLE IF NOT EXISTS feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL CHECK (kind IN ('broken','confusing','idea','love')),
    message         TEXT NOT NULL,
    screen          TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','read')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_feedback_time ON feedback(created_at);

-- Questions people ask the in-app helper (digits masked), so the team can see what confuses people.
-- Deleted with the account.
CREATE TABLE IF NOT EXISTS help_questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question        TEXT NOT NULL,
    lang            TEXT NOT NULL DEFAULT 'en',
    answered        INTEGER NOT NULL DEFAULT 1,
    screen          TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_help_time ON help_questions(created_at);

-- ─── Kitna Rent: for PG, hostel and flat owners ─────────────────────────────
-- Tenants pay the owner's own UPI ID as they always do (no gateway, no fee). Kitna reads the owner's bank
-- alerts, works out whose rent each payment is, and keeps every tenant's balance.
CREATE TABLE IF NOT EXISTS rent_properties (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    upi_id          TEXT NOT NULL DEFAULT '',
    due_day         INTEGER NOT NULL DEFAULT 5 CHECK (due_day BETWEEN 1 AND 28),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rent_prop_user ON rent_properties(user_id);

CREATE TABLE IF NOT EXISTS rent_tenants (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id     INTEGER NOT NULL REFERENCES rent_properties(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    phone           TEXT NOT NULL DEFAULT '',
    room            TEXT NOT NULL DEFAULT '',
    rent            INTEGER NOT NULL CHECK (rent > 0),          -- paise per month
    payer_names     TEXT NOT NULL DEFAULT '',                   -- who else pays for them, e.g. "Suresh Sharma" (father)
    start_month     TEXT NOT NULL,                              -- YYYY-MM: first month rent is due
    opening_due     INTEGER NOT NULL DEFAULT 0,                 -- paise owed before Kitna (old dues)
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','left')),
    left_month      TEXT,                                       -- YYYY-MM: last month rent was due
    token           TEXT NOT NULL UNIQUE,                       -- the tenant's own link (/r/<token>)
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rent_tenants_user ON rent_tenants(user_id, status);

CREATE TABLE IF NOT EXISTS rent_payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id       INTEGER NOT NULL REFERENCES rent_tenants(id) ON DELETE CASCADE,
    amount          INTEGER NOT NULL CHECK (amount > 0),
    date            TEXT NOT NULL,
    method          TEXT NOT NULL DEFAULT 'upi' CHECK (method IN ('upi','cash','bank')),
    how             TEXT NOT NULL DEFAULT 'auto' CHECK (how IN ('auto','tapped','manual')),
    transaction_id  INTEGER UNIQUE REFERENCES transactions(id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rent_pay_tenant ON rent_payments(tenant_id, date);

-- "Payments from R K SHARMA are Rahul's rent": learned when the owner taps once.
CREATE TABLE IF NOT EXISTS rent_payers (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    payer_key       TEXT NOT NULL,
    tenant_id       INTEGER NOT NULL REFERENCES rent_tenants(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, payer_key)
);

-- Money in that the owner said is NOT rent (so Kitna stops asking).
CREATE TABLE IF NOT EXISTS rent_not_rent (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    transaction_id  INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, transaction_id)
);

-- ─── Billing (Razorpay) ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS billing_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    order_id        TEXT NOT NULL UNIQUE,                       -- Razorpay order_xxx
    plan            TEXT NOT NULL,
    amount          INTEGER NOT NULL,                           -- paise
    months          INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created','paid','failed')),
    payment_id      TEXT,
    paid_at         TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_billing_user ON billing_orders(user_id);
