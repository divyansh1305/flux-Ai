# Kitna Companion (Android)

A tiny Android app (about 440 lines of Kotlin, no third-party libraries) that logs your UPI and bank payments into Kitna automatically. It reads **payment notifications**, so it needs no SMS permission.

```
Payment app notification ──► NotificationListenerService
                             │  on-device Filter: allow-listed app + ₹ amount +
                             │  "debited/paid/received", drops OTPs/offers/reminders
                             ▼
                      Uploader (retry queue, max 200)
                             │  HTTPS, Authorization: Bearer flx_…
                             ▼
              POST /api/ingest/notification  (Kitna server)
                             │  upi-parse → dedupe (UTR / amount±1 day) →
                             ▼  ledger + bank balance snapshot
                        Your dashboard
```

## Build it (10 minutes)

1. Install **Android Studio** (Ladybug or newer).
2. Choose **File → Open** and select this `android/` folder. Let Gradle sync. If it asks to create a Gradle wrapper, click **OK**.
3. Plug in an Android phone with USB debugging on, then press **Run ▶**.
   - Or use **Build → Build APK(s)** and install the APK from `app/build/outputs/apk/`.

## Link it

1. In Kitna on the web, go to **Settings → Auto-log → Create token** and copy the `flx_…` token. It is shown only once.
2. In the app:
   - Read the disclosure and tick the consent box.
   - Paste your server URL (`https://…onrender.com`) and the token.
   - Tap **Save & test connection**. It should say "Connected as <name>".
3. Tap **Open Notification access settings**, then turn on **Kitna Companion**.
4. Make a ₹1 UPI payment. It appears in Kitna within a few seconds.

## Security choices (good interview material)

| Risk | What the app does |
|---|---|
| Token stolen from the phone | AES-256-GCM encrypted with a key held in the Android Keystore. Excluded from cloud backup and device transfer. |
| Private chats or OTPs leaking | Allow-listed packages only, plus an on-device filter. Anything else never leaves the phone. The server checks the package list again. |
| Duplicate entries (SMS + notification + retries) | The server dedupes by UPI reference, or by same amount within ±1 day from a different source. |
| Offline | Payments are queued locally (max 200) and retried. 4xx responses are dropped, while 5xx and 429 responses are retried. |
| Lost phone | Revoke the token in Kitna. Tap **Unlink** in the app. |
| Cleartext traffic | `usesCleartextTraffic=false`, and only `https://` URLs are accepted. |

## Google Play notes

- Google Play restricts SMS permissions, so this app deliberately uses **notification access** instead.
- Notification access is allowed when it is the core feature and you show a **prominent disclosure** plus consent before asking for it. The first screen does exactly this.
- In the Play Console Data safety form, declare:
  - "Financial info → purchase history" is collected and sent to your server.
  - Data is encrypted in transit.
  - Users can request deletion. Account deletion in Kitna removes everything.
- You also need a privacy policy URL. Kitna serves one at `/privacy`.

## Keep in sync

`Filter.PACKAGES` must match `PACKAGES` in `packages/upi_parse/src/upi_parse/notification.py`.
