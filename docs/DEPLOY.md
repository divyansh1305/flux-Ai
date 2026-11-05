# Deploying Kitna on PythonAnywhere (free)

Kitna runs at `https://fluxai.pythonanywhere.com` from the code in `~/flux-ai`.

## Every update (2 minutes)

1. PythonAnywhere → **Consoles** → **Bash** (close an old console first if you hit the limit).
2. Run:
   ```bash
   cd ~/flux-ai && git pull
   ~/.virtualenvs/flux/bin/pip install -r requirements.txt   # only needed if requirements.txt changed
   ```
   **This update (reminders, friends, PDF statements) changed `requirements.txt`: run the pip line.** It adds the PDF reader.
3. **Web** tab → green **Reload** button.
4. Open the site. The database updates itself; phones pick up the new version on their own (open Kitna twice).

## Settings file: `/home/fluxAI/.env`

| Setting | What to put |
|---|---|
| `SECRET_KEY` | a long random string (already set; never change it, or everyone is signed out and Gmail links stop working) |
| `FLUX_ENV` | `production` |
| `EMAIL_SENDER`, `EMAIL_PASSWORD` | Gmail address + its App Password, for sign-in codes |
| `GEMINI_API_KEY` | for Ask Kitna answers |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | for Google sign-in and Connect Gmail |
| `ADMIN_EMAILS` | **your** sign-in email, so only you can open `/app/admin` (Kitna numbers) |
| `METRICS_TOKEN` | optional: a long password for `/metrics` |
| `APP_TIMEZONE` | `Asia/Kolkata` |
| `VAPID_PRIVATE_KEY` | optional. Leave empty: Kitna creates its reminder key in `instance/vapid_private.key` on first use. Back that file up; if it is lost, everyone has to turn reminders on again. |

After changing `.env`, press **Reload** on the Web tab.

## Once

- **Google Cloud → OAuth consent screen → Audience → Publish app.** Testing mode makes every Gmail connection expire after 7 days. Users will still see "Google hasn't verified this app" until Google's security review (needed before 100 users).
- **Tasks tab → daily task** (one free task), at **03:15 UTC** (8:45 am in India):
  ```bash
  cd ~/flux-ai && ~/.virtualenvs/flux/bin/python scripts/daily.py
  ```
  It backs up the database, checks everyone's Gmail, sends the day's reminders (at most 3 per person), and works out
  yesterday's totals for Kitna numbers. Already set it for another time? Edit the time on the Tasks tab.
- Reminders reach phones through `fcm.googleapis.com` (Android/Chrome) and `web.push.apple.com` (iPhone). Both are on
  PythonAnywhere's free allowlist. iPhone users must add Kitna to the Home Screen first (iOS 16.4+).

## Every month

- **Web** tab → **Run until 1 month from today**. If you forget, the site stops until you click it.

## Where to look

| What | Where |
|---|---|
| Kitna numbers (sign-ups, where setup stops, who comes back, which sources work, ₹ kept) | `https://fluxai.pythonanywhere.com/app/admin` (only for `ADMIN_EMAILS`) |
| Errors | Web tab → **Error log** (search for the request ID) |
| Every request | Web tab → **Server log** |
| Raw totals by hand | Bash: `sqlite3 ~/flux-ai/instance/flux.db` then e.g. `SELECT COUNT(*) FROM users;` |
| Live counters | `/metrics` with `Authorization: Bearer <METRICS_TOKEN>` |
| Reminders sent | Bash: `sqlite3 ~/flux-ai/instance/flux.db "SELECT kind, COUNT(*), SUM(pushed) FROM notifications GROUP BY kind;"` |
| Android app download | GitHub → Releases → `android-latest` (rebuilt on every push that changes `android/`) |

## Optional: move to `kitna.pythonanywhere.com` (about 30 minutes)

The app is called Kitna, but the address is still `fluxai.pythonanywhere.com` because a free PythonAnywhere address is
your account name. Everything keeps working at the old address; move only when you're ready, ideally **before** you
invite friends so nobody has to switch.

1. Sign up for a new free PythonAnywhere account with the username **`kitna`** (if it's taken, pick `kitnaapp`, and use
   that name below).
2. In its Bash console: `git clone https://github.com/divyansh1305/flux-Ai.git ~/flux-ai`, then make the virtualenv
   and the web app exactly as in the first setup (same WSGI file, source `~/flux-ai`, virtualenv `~/.virtualenvs/flux`).
3. Copy from the **old** account (Files tab → download, then upload in the new one):
   - `/home/fluxAI/.env` → `/home/kitna/.env`. Keep the same `SECRET_KEY`.
   - `~/flux-ai/instance/flux.db` (everyone's data) and `~/flux-ai/instance/vapid_private.key` (so phones keep reminders).
4. Google Cloud → Credentials → your OAuth client: add `https://kitna.pythonanywhere.com` to **Authorised JavaScript
   origins** and `https://kitna.pythonanywhere.com/gmail/callback` to **Authorised redirect URIs**.
5. Reload the new web app, sign in, check Home. The Android Companion already accepts the new address.
6. On the old account, stop the web app (or leave it until everyone has moved) and set the daily task only on the new one.

## Optional: rename the GitHub repo to `kitna`

GitHub → the repo → **Settings → General → Repository name** → `kitna` → Rename. GitHub redirects the old address, so
`git pull` on PythonAnywhere and the Android download link keep working. Then set
`ANDROID_APK_URL=https://github.com/divyansh1305/kitna/releases/download/android-latest/kitna-android.apk` in `.env`.

## Off-site backup and the signed Android app (one time, about 5 minutes)

You received `KITNA-SECRETS-to-add.txt` and `kitna-release.jks`. Keep both private.

1. **GitHub → the repo → Settings → Secrets and variables → Actions → New repository secret.** Add the seven secrets
   from the file: `ANDROID_KEYSTORE_B64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`,
   `FLUX_URL`, `BACKUP_TOKEN`, `BACKUP_PASSPHRASE`.
2. **PythonAnywhere `.env`:** add `BACKUP_TOKEN=…` (same value) and
   `BACKUP_DIR=/home/fluxAI/flux-ai/instance/backups`, then **Reload**.
3. **GitHub → Actions:** run **off-site backup** (it should go green with an artifact), then **android** (its log
   should say "Signed release build.").

What you get:
- Every day at 09:47 IST, GitHub downloads the newest backup, encrypts it with your passphrase and keeps 30 days of
  copies. If PythonAnywhere ever loses the account, the data survives.
- Kitna Companion is signed with your own key. Note: the first signed version can't update the old test build in
  place, so uninstall Kitna Companion once and install it again.
- Restore: download the artifact, then `gpg -d flux-backup.db.gpg > flux.db` (asks for the passphrase), upload as
  `~/flux-ai/instance/flux.db`, Reload.

Optional `.env` line: `CONTACT_EMAIL=you@example.com` sets the support/grievance address shown on the privacy and terms
pages (otherwise the sign-in email sender is used).
