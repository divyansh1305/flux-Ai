# Go-live setup: exact steps

Do these in order. ⏱ about 2–3 hours in total. If anything fails, copy the error and send it to Claude.

---

## 1. Gemini key (10 min)
1. Open https://aistudio.google.com/apikey.
2. **Delete every old key.** They were in the old project's code, so treat them as leaked.
3. Click **Create API key** and save it in your notes app for now.

## 2. Gmail app password, for sign-in codes (10 min)
1. Use a new Gmail account such as `flux.app.mail@gmail.com`, so your personal inbox stays private.
2. Go to https://myaccount.google.com/security and turn on **2-Step Verification**.
3. Go to https://myaccount.google.com/apppasswords, create one named "Flux" and copy the 16 letters (no spaces).

## 3. GitHub (15 min)
1. On https://github.com/new, create **flux** as a **Private** repo with no README.
2. In Terminal on your Mac:
```bash
cd ~/Desktop/flux-v2
git init
git add .
git status
```
3. **Check the list.** You must NOT see `.env`, `instance/`, `.venv/`, any `.db` file or `statement.csv`. You SHOULD see `.github/workflows/tests.yml` and `backup.yml`.
4. Commit and push (replace YOUR-NAME):
```bash
git commit -m "Flux v2"
git branch -M main
git remote add origin https://github.com/YOUR-NAME/flux.git
git push -u origin main
```
5. Open the **Actions** tab on GitHub. The "tests" run should turn ✅ green in about 3 minutes.

## 4. Render (20 min)
1. On https://render.com, sign up with GitHub.
2. Choose **New → Blueprint**, pick the `flux` repo and click **Apply**.
3. When it asks for values, fill in:

| Key | Value |
|---|---|
| `EMAIL_SENDER` | the Gmail address from step 2 |
| `EMAIL_PASSWORD` | the 16-letter app password |
| `GEMINI_API_KEY` | the key from step 1 |
| `GOOGLE_CLIENT_ID` | leave empty for now (step 6) |
| `KITE_API_KEY` | leave empty (investing runs in practice mode) |

4. The plan is **Starter**. The disk that stores user data needs a paid plan, about $7/month.
5. Wait for "Live", then open `https://YOUR-APP.onrender.com/readyz`. It should show `{"db":"up","ok":true}`.
6. Sign up on your own site. The sign-in code arrives by email.

## 5. Off-site backups (5 min)
1. In Render, go to your service → **Environment** and reveal `BACKUP_TOKEN`. Copy it.
2. In GitHub, go to the repo → **Settings → Secrets and variables → Actions → New repository secret** and add three:
   - `FLUX_URL` = `https://YOUR-APP.onrender.com`
   - `BACKUP_TOKEN` = the value you just copied
   - `BACKUP_PASSPHRASE` = a long password. **Save it somewhere safe. Without it, backups can't be opened.**
3. Go to **Actions → off-site backup → Run workflow**. It should go ✅ (the app makes its first backup a few minutes after starting).

Restoring a backup: download the artifact, run `gpg -d flux-backup.db.gpg > flux.db`, and send the file to Claude for help putting it back.

## 6. Google Sign-In (optional, 15 min)
1. Go to https://console.cloud.google.com, create a project called "Flux", then **APIs & Services → OAuth consent screen**. Choose External and fill in the app name and your email.
2. Under **Credentials → Create credentials → OAuth client ID**, choose Web application.
3. For **Authorised JavaScript origins**, add `https://YOUR-APP.onrender.com`.
4. Copy the Client ID into Render as `GOOGLE_CLIENT_ID`. Render redeploys by itself.

## 7. Phones (30–60 min)
**Android:**
1. Install Android Studio and open the `android/` folder.
2. Plug in a phone (Settings → About → tap Build number 7 times → Developer options → USB debugging) and press ▶ Run.
3. In Flux on the web, go to Settings → Automatic tracking and create a token.
4. In the app:
   - Tick consent.
   - Paste `https://YOUR-APP.onrender.com` and the token.
   - Tap **Test connection**.
   - Tap **Open Notification access** and turn on Flux.
5. Pay ₹1 to a friend by UPI. It should appear in Flux within seconds.

**iPhone:** follow the Shortcuts steps shown in Settings on the live site.

## 8. Cloudflare protection (optional, 30 min, needs a domain)
Do this once you buy a domain (for example `getflux.in`, about ₹600/year).
1. Add the domain to Cloudflare's free plan and change the nameservers at your registrar to Cloudflare's.
2. In Render, go to **Settings → Custom domains**, add `app.getflux.in` and note the target.
3. In Cloudflare **DNS**, add a CNAME `app` pointing to that target. Keep it **DNS only (grey cloud)** until Render shows "Verified" and the certificate is issued, then switch it to **Proxied (orange cloud)**.
4. In Cloudflare, go to **SSL/TLS** and set the mode to **Full (strict)**.
5. In Render **Environment**, add `TRUSTED_PROXY_HOPS = 2`. **This step is important.** Without it, every user looks like the same Cloudflare IP to the rate limiter.
6. In Cloudflare, go to **Security → Bots** and turn on **Bot Fight Mode**.
7. Update the Google Sign-In origin and the Android or Shortcut URL to the new domain.

## 9. Before inviting friends: checklist
- [ ] The GitHub Actions "tests" run is green.
- [ ] `/readyz` shows ok.
- [ ] A sign-in email arrives within a minute (check spam the first time).
- [ ] A ₹1 UPI payment logs automatically from the phone.
- [ ] The dashboard says "Bank says … in sync" after two bank SMS, or after you click "Match my bank".
- [ ] The off-site backup run is green.
- [ ] Your own account works for 2–3 days with no surprises.

Then send the messages in `docs/LAUNCH_MESSAGES.md`.
