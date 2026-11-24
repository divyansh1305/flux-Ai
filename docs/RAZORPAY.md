# Turning on payments (Razorpay) for Kitna Rent Pro

Kitna Rent is free for up to 5 tenants. Pro (₹299 / month or ₹2,999 / year, up to 100 tenants, no auto-renewal)
is sold through Razorpay Standard Checkout. Until the keys below are set, the upgrade screen says "Pro opens soon".

## 1. Create the Razorpay account (owner does this)
1. Sign up at razorpay.com with the Kitna email. Business type: **Individual / Unregistered** is fine to start
   (needs PAN and a bank account in your name).
2. Website: `https://getkitna.vercel.app`. Razorpay checks these pages exist (they do):
   `/terms`, `/privacy`, `/refunds` (cancellation & refund + delivery), `/contact`, and pricing on the home page.
3. Finish KYC. Test mode works immediately; live mode after Razorpay approves the account.

## 2. Keys → Vercel (Settings → Environment Variables, Production)
| Key | Where in Razorpay |
|---|---|
| `RAZORPAY_KEY_ID` | Account & Settings → API Keys (starts `rzp_test_` or `rzp_live_`) |
| `RAZORPAY_KEY_SECRET` | Shown once when you generate the key |
| `RAZORPAY_WEBHOOK_SECRET` | Any long random text you choose in step 3 |

## 3. Webhook (so a closed tab never loses a payment)
Account & Settings → Webhooks → Add:
- URL: `https://getkitna.vercel.app/api/billing/webhook`
- Secret: the same text as `RAZORPAY_WEBHOOK_SECRET`
- Events: `order.paid`, `payment.captured`

Redeploy after adding the variables.

## How it's safe
- The server sets the price; the browser only picks a plan id.
- The plan is given only after the HMAC-SHA256 signature checks out (checkout) or the webhook signature checks out.
- Each order can extend the plan once, whichever arrives first. Tests: `tests/test_rent.py`.
- Tenants' rent never goes through Razorpay or Kitna; only the owner's Pro fee does.
