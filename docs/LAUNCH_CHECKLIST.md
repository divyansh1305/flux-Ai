# Kitna launch checklist

*Pehle Kitna, phir kharcha.*

## Already done and tested (6 Nov 2026)

- 202 automated tests pass, locally and on GitHub on every push.
- **Screens:** all 16 checked on a phone and a laptop, in light and dark mode (66 screen checks), plus 12 more on the
  pages people see before signing in. No JavaScript errors, no failed requests, no sideways scrolling. Text meets the
  4.5:1 readability rule, and buttons are at least 40–44 px to tap.
- **Real-user walkthrough:** 17 steps tapped through the screens on a phone, all passing (`scripts/qa/e2e.py`):
  - sign up with an email code
  - onboarding
  - add an expense, add a plan
  - split with a friend, and get ticked off automatically by the friend's bank SMS
  - set a budget, create a goal
  - CSV statement, and a password-protected PDF (wrong password, then the right one)
  - paste an SMS
  - ask Kitna a question
  - Hinglish on and off
  - UPI ID, reminder settings, reminders inbox
  - download my data, delete my account
- **Brand:** the Kitna logo, icon, colours and tagline are on every screen, email, icon, notification and share
  preview. The logo kit is in `brand/`.

## Bugs found and fixed in this pass

- "Download my data" didn't download: the export was read as data, not as a file.
- Changing the language on one device didn't switch another device until sign-out.
- A friend who paid their share a day before the bill was dated wasn't ticked off.
- Ask: the question box was at the bottom of a long page. It's now at the top.
- Plans and Friends: names were cut off and buttons wrapped on phones. Buttons now sit on their own line.
- Grey secondary text was too faint to read outdoors (contrast 3.6, now 5).
- Small tap targets: delete, done and remove buttons, and text links.
- Dark mode had the old greenish greys, and a few old colours were left over.
- Coach showed a raw date ("2026-12-03").

## Before you invite people

1. **Deploy:** in a PythonAnywhere Bash console:
   `cd ~/flux-ai && git pull && ~/.virtualenvs/flux/bin/pip install -r requirements.txt`, then **Reload** on the
   Web tab.
2. **Address:** move to `kitna.pythonanywhere.com` (steps in `DEPLOY.md`) *before* sharing the link, so nobody has
   to switch later.
3. **`.env`:** set `ADMIN_EMAILS=<your email>`, and check that `SECRET_KEY`, `EMAIL_SENDER`, `EMAIL_PASSWORD`,
   `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set. Then Reload.
4. **Google Cloud → OAuth consent screen → Publish app.** Add the new address to the allowed origins and redirect
   URIs.
5. **Tasks tab:** daily task at **03:15 UTC**:
   `cd ~/flux-ai && ~/.virtualenvs/flux/bin/python scripts/daily.py`.
6. **Your own phones** (I can't test these from a server):
   - iPhone: Safari → Share → Add to Home Screen, open from the icon, Settings → Reminders → Turn on. A test
     notification should arrive.
   - Android: Chrome → install, turn on reminders, and install Kitna Companion from Settings → Android.
   - Make one real UPI payment of ₹1. It should show up by itself (Gmail on iPhone, Companion on Android).
7. **Share preview:** paste your link in a WhatsApp chat. You should see the Kitna image with the tagline.

## Launch week

- Start with 5 friends, then 20. Don't post publicly until the privacy page has been read by someone with legal
  knowledge.
- Check `/app/admin` daily: where setup stops, whether payments are being read (SMS / email), and errors.
- When a bank message isn't read, ask for the text with the amounts and names hidden, and add it to the parser.
- Renew PythonAnywhere every month (Web tab → "Run until 1 month from today").

## Known limits to say honestly

- Gmail allows 100 users until Google's security review (CASA). People see "Google hasn't verified this app" until
  then.
- The Android Companion is installed from a link, not the Play Store, so Android shows a warning.
- iPhone notifications work only from the Home Screen icon (iOS 16.4+).
- The bank message reader hasn't yet been used at scale: new banks and formats will turn up.
