# Deploying Flux on PythonAnywhere (free)

Flux runs at `https://fluxai.pythonanywhere.com` from the code in `~/flux-ai`.

## Every update (2 minutes)

1. PythonAnywhere → **Consoles** → **Bash** (close an old console first if you hit the limit).
2. Run:
   ```bash
   cd ~/flux-ai && git pull
   ~/.virtualenvs/flux/bin/pip install -r requirements.txt   # only needed if requirements.txt changed
   ```
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

After changing `.env`, press **Reload** on the Web tab.

## Once

- **Google Cloud → OAuth consent screen → Audience → Publish app.** Testing mode makes every Gmail connection expire after 7 days. Users will still see "Google hasn't verified this app" until Google's security review (needed before 100 users).
- **Tasks tab → daily task** (one free task):
  ```bash
  cd ~/flux-ai && ~/.virtualenvs/flux/bin/python scripts/daily.py
  ```
  It backs up the database, checks everyone's Gmail, and works out yesterday's totals for Flux numbers.

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
| Android app download | GitHub → Releases → `android-latest` (rebuilt on every push that changes `android/`) |
