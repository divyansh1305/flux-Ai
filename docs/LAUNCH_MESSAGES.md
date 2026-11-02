# Messages for your first users

Change the link and your name. Send them personally; that works far better than a group blast.

## 1. To close friends, one by one (WhatsApp)

> Hey! I built an app called Flux that tracks every UPI payment **automatically**. No typing. GPay, PhonePe, Paytm, bank SMS, everything gets logged by itself, and it tells you how much you can safely spend today.
>
> I need 10 people to try it for 2 weeks and tell me what's annoying. It takes 5 minutes to set up and I'll help you on call.
>
> It never asks for your UPI PIN or bank password, and it can't move your money.
> 👉 https://YOUR-APP.onrender.com
>
> In?

## 2. College / hostel group (after 10 friends are happy)

> 💸 **Where did my money go this month?** Flux answers that automatically.
>
> • Logs GPay / PhonePe / Paytm / bank payments by itself (Android app + iPhone shortcut)
> • "Safe to spend today: ₹412", based on your bills and goals
> • Rounds up every payment into a savings goal
> • Talk to it: "aaj kitna kharch kar sakta hoon?"
>
> Built by me (CSE, [college]). Free, no ads, and your data is never sold. You can export or delete it any time.
> Try it: https://YOUR-APP.onrender.com. Feedback welcome!

## 3. Feedback check-in, day 7

> Hey, quick 2 questions about Flux:
> 1. Did any payment NOT get logged, or get logged wrong? (a screenshot helps a lot)
> 2. What's the one thing you'd change?
>
> Also, if you're okay with it: Settings → "Help improve accuracy" keeps a masked copy of payment messages (no names, numbers or accounts). After a week, tap "Download my masked samples" and send me the file. It helps me fix bank formats Flux doesn't know yet 🙏

## 4. LinkedIn post (after about 30 users)

> I built Flux, an automatic money tracker for UPI users, and launched it to N students.
>
> The hard part wasn't the UI. It was **correctness**: one payment shows up as a Scan & Pay, a GPay notification, a bank SMS and a statement row. Flux matches them into one, reconciles against the balance your bank reports, and measures its own categorisation accuracy from users' corrections (currently X%).
>
> Stack: Flask, SQLite (WAL), a Kotlin Android companion, and an open-source parser library (upi-parse). Load-tested at 228 req/s, p95 116 ms.
>
> Three bugs the load test caught before users did: 🧵
