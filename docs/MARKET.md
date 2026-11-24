# Kitna: market and competitor notes (Nov 2026)

## The market

- UPI processed **24.5 billion transactions in August 2026** (₹29.8 lakh crore), about 800 million a day. PhonePe (~46%) and Google Pay (~32%) carry most of it. Source: NPCI monthly data.
- Most of those are small payments (chai, auto, food), the kind nobody writes down. That is the gap Kitna fills.
- Over 95% of Indian smartphones run Android, so automatic tracking has to work well on Android first.

## Who already does this

| App | What it does well | Where it falls short (Kitna's opening) |
|---|---|---|
| **axio (ex-Walnut)** | 1.4 crore+ installs, SMS auto-tracking | Now sells pay-later, personal loans and FDs. Users who want a tracker get loan offers. |
| **INDmoney / Fold** | Net worth, investments, Account Aggregator bank sync | Built for investors and salaried users, heavy for a student who pays ₹60 for chai |
| **Fi / Jupiter** | Auto-tracking, but only for their own bank account | You have to move your bank |
| **Money Manager (Realbyte)** | Simple, 1 crore+ installs | Fully manual, people stop after a week |
| **Trackk, Splitwise** | Splitting with friends | Not a daily money view |
| **New SMS trackers (Vrid, Finny, iLekka...)** | Auto-tracking | They look back ("you spent ₹X"), not forward ("you can spend ₹X today") |

## Kitna's position

**"Pehle Kitna, phir kharcha."** Every other app tells you what you already spent. Kitna tells you what you can still spend **today**, before you pay.

What makes it hard to copy:
1. **Safe to spend today**, built from your own payday, plans and cushion, not a generic budget.
2. **One ledger you can trust**: the same ₹347 seen in a UPI notification, a bank SMS, Gmail and a statement is stored once, and checked against the bank's own balance.
3. **Money checks**: failed payments watched until the refund arrives (RBI timelines), double charges, subscription price rises.
4. **No loans, no ads, never moves money.** This is the trust gap axio left.

## Why notification access, not SMS permission

Google Play only lets apps read SMS if they are the default SMS, phone or assistant app. Finance trackers keep getting rejected. Kitna's Android companion reads payment **notifications** instead (allowed with a clear disclosure), which covers both UPI apps and the SMS app's notification of a bank SMS.

## What we cut and why

The app had grown 19 screens. The new navigation keeps only what supports the one number:

| Kept, in the tab bar | Moved under "You" | Removed from navigation |
|---|---|---|
| Today (safe-to-spend + Just paid), Activity, Plan, You | Friends (split and get paid back), Ask Kitna, add a bank statement, settings | Monthly limits and savings goals: they compete with the one number and confused testers. The code stays so nobody's data is lost. |

## Business model (later, once people use it daily)

- Free: everything above.
- **Kitna Plus (₹49/month)**: unlimited statement imports, family view, export. Never loans, never selling data.

## What to measure with the first users

- Day-7 retention: are they still opening it a week later?
- Capture rate: what share of their real payments did Kitna log by itself?
- "Did today's number change what you spent?" (yes/no, in-app, once a week)
