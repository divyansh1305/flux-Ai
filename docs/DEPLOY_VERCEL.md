# Deploying Kitna on Vercel (free, nothing to renew)

Kitna runs on **Vercel** (the app) + **Turso** (the database, a hosted SQLite). Both have free plans
with nothing to renew. You push to GitHub and the site updates by itself.

Why Turso: Vercel has no lasting disk, so the old `flux.db` file would be wiped on every deploy.
Turso runs the same SQLite, so all of Kitna's queries work unchanged (every test passes on it).

## One-time setup (about 30 minutes)

### 1. Turso (database)
1. Sign up at **turso.tech** with GitHub.
2. Create a database named `kitna`. Pick the region closest to India (Mumbai if offered), so it is next to the Vercel servers.
3. Copy its **URL** (`libsql://kitna-<you>.turso.io`) and create a **token** (Database → Create token). Keep both private.

### 2. Secrets you'll paste into Vercel
On your laptop, in the project folder:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"   # CRON_SECRET
python scripts/make_vapid_key.py                                # VAPID_PRIVATE_KEY
```
If you already have a `SECRET_KEY` on PythonAnywhere, reuse it (otherwise Gmail links have to be reconnected).

### 3. Vercel (app)
1. Sign up at **vercel.com** with GitHub → **Add New → Project** → import `divyansh1305/flux-ai`.
2. Framework preset: **Flask** (Vercel finds `app.py`). Leave the build settings as they are.
3. **Environment Variables**, then **Deploy**:

| Name | Value |
|---|---|
| `FLUX_ENV` | `production` |
| `SECRET_KEY` | from step 2 |
| `TURSO_DATABASE_URL` | `libsql://kitna-<you>.turso.io` |
| `TURSO_AUTH_TOKEN` | the Turso token |
| `CRON_SECRET` | from step 2 (Vercel sends it to the daily job) |
| `VAPID_PRIVATE_KEY` | from step 2 (never change it) |
| `ADMIN_EMAILS` | your sign-in email |
| `APP_TIMEZONE` | `Asia/Kolkata` |
| `EMAIL_SENDER`, `EMAIL_PASSWORD` | Gmail + App Password, for sign-in codes |
| `GEMINI_API_KEY` | for Ask Kitna and the helper in 11 languages |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | for Google sign-in and Connect Gmail |
| `ANDROID_APK_URL` | optional, where the Android app download points |

4. Your site is at `https://<project>.vercel.app` (Settings → Domains lets you pick `kitna.vercel.app` if it's free, or add your own domain later).

### 4. Google sign-in and Gmail
Google Cloud Console → **Credentials** → your OAuth client:
- **Authorised JavaScript origins:** add `https://<project>.vercel.app`
- **Authorised redirect URIs:** add `https://<project>.vercel.app/gmail/callback`

### 5. Bring your existing users (optional)
1. On PythonAnywhere: **Files** → download `flux-ai/instance/flux.db`.
2. On your laptop:
```bash
TURSO_DATABASE_URL=libsql://... TURSO_AUTH_TOKEN=... python scripts/copy_to_turso.py flux.db
```
3. On PythonAnywhere's `.env`, set `MOVED_TO=https://<project>.vercel.app` and Reload, so old links forward to the new site. After that, PythonAnywhere can expire: nothing depends on it.

## Every update after that
`git push` to `main`. Vercel builds and deploys by itself in about a minute. Database tables update themselves.

## The daily job
`vercel.json` runs `/api/cron/daily` every day at 03:15 UTC (8:45 am India): Gmail for everyone, reminders,
yesterday's numbers. Gmail also syncs whenever someone opens Kitna, so nobody waits for the daily job.
Check it: Vercel → Project → **Settings → Cron Jobs** (you can press Run).

## Good to know
- **Free limits:** Vercel's Hobby plan is for personal, non-commercial projects. If Kitna starts charging money, move to Vercel Pro (or any host that runs Python).
- **Backups:** Turso keeps point-in-time backups. Kitna's own file backups (`BACKUP_DIR`) are not used on Vercel.
- **Speed:** keep the database and the app in the same region (`vercel.json` pins the app to Mumbai, `bom1`).
- **Rate limits** are counted per server instance on Vercel, so they are a little looser than on one server.
