# Deploying Flux on PythonAnywhere (free)

Flux runs at `https://fluxai.pythonanywhere.com` from the code in `~/flux-ai`.

## Every update (2 minutes)

1. PythonAnywhere → **Consoles** → **Bash** (close an old console first if you hit the limit).
2. Run:
   ```bash
   cd ~/flux-ai && git pull
   ~/.virtualenvs/flux/bin/pip install -r requirements.txt   # only needed if requirements.txt changed
   ```
   **This update (reminders, friends, PDF statements) changed `requirements.txt`: run the pip line.** It adds the PDF reader.
3. **Web** tab → green **Reload** button.
4. Open the site. The database updates itself; phones pick up the new version on their own (open Flux twice).

## Settings file: `/home/fluxAI/.env`

| Setting | What to put |
|---|---|
| `SECRET_KEY` | a long random string (already set; never change it, or everyone is signed out and Gmail links stop working) |
| `FLUX_ENV` | `production` |
| `EMAIL_SENDER`, `EMAIL_PASSWORD` | Gmail address + its App Password, for sign-in codes |
| `GEMINI_API_KEY` | for Ask Flux answers |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | for Google sign-in and Connect Gmail |
| `ADMIN_EMAILS` | **your** sign-in email, so only you can open `/app/admin` (Flux numbers) |
| `METRICS_TOKEN` | optional: a long password for `/metrics` |
| `APP_TIMEZONE` | `Asia/Kolkata` |
| `VAPID_PRIVATE_KEY` | optional. Leave empty: Flux creates its reminder key in `instance/vapid_private.key` on first use. Back that file up; if it is lost, everyone has to turn reminders on again. |

After changing `.env`, press **Reload** on the Web tab.

## Once

- **Google Cloud → OAuth consent screen → Audience → Publish app.** Testing mode makes every Gmail connection expire after 7 days. Users will still see "Google hasn't verified this app" until Google's security review (needed before 100 users).
- **Tasks tab → daily task** (one free task), at **03:15 UTC** (8:45 am in India):
  ```bash
  cd ~/flux-ai && ~/.virtualenvs/flux/bin/python scripts/daily.py
  ```
  It backs up the database, checks everyone's Gmail, sends the day's reminders (at most 3 per person), and works out
  yesterday's totals for Flux numbers. Already set it for another time? Edit the time on the Tasks tab.
- Reminders reach phones through `fcm.googleapis.com` (Android/Chrome) and `web.push.apple.com` (iPhone). Both are on
  PythonAnywhere's free allowlist. iPhone users must add Flux to the Home Screen first (iOS 16.4+).

## Every month

- **Web** tab → **Run until 1 month from today**. If you forget, the site stops until you click it.

## Where to look

| What | Where |
|---|---|
| Flux numbers (sign-ups, where setup stops, who comes back, which sources work, ₹ kept) | `https://fluxai.pythonanywhere.com/app/admin` (only for `ADMIN_EMAILS`) |
| Errors | Web tab → **Error log** (search for the request ID) |
| Every request | Web tab → **Server log** |
| Raw totals by hand | Bash: `sqlite3 ~/flux-ai/instance/flux.db` then e.g. `SELECT COUNT(*) FROM users;` |
| Live counters | `/metrics` with `Authorization: Bearer <METRICS_TOKEN>` |
| Reminders sent | Bash: `sqlite3 ~/flux-ai/instance/flux.db "SELECT kind, COUNT(*), SUM(pushed) FROM notifications GROUP BY kind;"` |
| Android app download | GitHub → Releases → `android-latest` (rebuilt on every push that changes `android/`) |
