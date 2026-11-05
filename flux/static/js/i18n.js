/* Kitna in Hinglish (Settings → Language). Turns on only when the user picks it.
   How: the screens are written in English; this swaps whole sentences for their Hinglish version as they appear
   (exact matches, plus patterns for sentences with numbers in them). User data (merchant names, notes) never
   matches a sentence here, so it is left alone. Covers Home, Activity, Plans, Friends, reminders and common
   buttons; deeper settings stay in English. Server messages that change (reminders, the Sunday note) are
   written in Hinglish by the server itself. */
(function () {
  "use strict";

  const D = {
    // navigation and common buttons
    "Home": "Home", "Activity": "Hisaab", "Budgets": "Budget", "Goals": "Goals", "Plans": "Plans", "Friends": "Dost",
    "Coach": "Coach", "Ask": "Poocho", "Add": "Jodo", "Reminders": "Reminders", "Settings": "Settings",
    "Cancel": "Rehne do", "Close": "Band karo", "Delete": "Hatao", "Confirm": "Pakka", "Save": "Save karo", "Undo": "Wapas lo",
    "Edit": "Badlo", "Done": "Ho gaya", "Next": "Aage", "Yes": "Haan", "No": "Nahi", "See": "Dekho", "Later": "Baad mein",
    "Got it": "Samajh gaya", "Turn on": "Chalu karo", "Not now": "Abhi nahi", "Remove": "Hatao", "Removed.": "Hata diya.",
    "Saved.": "Save ho gaya.", "Deleted.": "Hata diya.", "Today": "Aaj", "Yesterday": "Kal", "Category": "Category",
    "Date": "Tareekh", "Amount (₹)": "Kitne (₹)", "Note (optional)": "Note (optional)", "Expense": "Kharcha", "Income": "Aamdani",
    "Something went wrong.": "Kuch gadbad ho gayi.", "You seem to be offline. Check your connection.": "Internet nahi chal raha. Connection check karo.",
    // Home
    "Good morning": "Good morning", "Safe to spend today": "Aaj safe kharcha", "Safe to spend today (about)": "Aaj safe kharcha (lagbhag)",
    "Add expense": "Kharcha jodo", "Add a plan": "Plan jodo", "How is this worked out?": "Yeh kaise nikla?", "Hide the maths": "Hisaab chhupao",
    "Spent today": "Aaj kharch hua",
    "Whatever you don't spend today stays in the pool, so tomorrow's number goes up.": "Aaj jo bachega woh kal ke number mein jud jayega.",
    "Make today's number yours": "Aaj ka number apna banao", "Your week": "Aapka hafta",
    "Get a heads-up on your phone": "Phone pe yaad dilaye Kitna",
    "Bills due tomorrow, late refunds, and when friends pay you back. At most 3 a day.": "Kal ke bills, late refund, aur jab dost paise lautayein. Din mein 3 se zyada nahi.",
    "Reminders are on.": "Reminders chalu.", "Reminders are on. You should see a test notification now.": "Reminders chalu. Ek test notification aana chahiye.",
    "Recent": "Haal ke payments", "See all": "Sab dekho", "No payments yet": "Abhi koi payment nahi",
    "Connect your payments in Settings, or tap Add expense.": "Settings mein payments jodo, ya Kharcha jodo dabao.",
    "This month": "Is mahine", "Details": "Details", "Spent": "Kharch", "Nothing yet this month": "Is mahine abhi kuch nahi",
    "Money in": "Aaye paise", "Set aside for goals": "Goals ke liye alag", "Still in your bank, not counted as spendable": "Bank mein hi hai, kharche mein nahi gina",
    "Where your money went": "Paise kahan gaye", "Nothing planned yet": "Abhi koi plan nahi",
    "Going out on Friday? Add it as a plan and Kitna keeps the money aside.": "Friday ko bahar ja rahe ho? Plan jodo, Kitna paise alag rakh dega.",
    "Your plan": "Aapka plan", "Maybe coming in": "Shayad aayega", "Repeats every month": "Har mahine", "Repeats every week": "Har hafte",
    "Your bank didn't say who sent it.": "Bank ne nahi bataya kisne bheja.", "Ticked off.": "Ho gaya, list se hata diya.",
    "Reconnect": "Dobara jodo", "Match": "Milao", "A payment may be missing. ": "Shayad ek payment chhoot gaya. ",
    // setup card (from the server)
    "Connect your payments": "Payments jodo", "Gmail on iPhone, the Kitna Companion app on Android": "iPhone pe Gmail, Android pe Kitna Companion app",
    "Tell Kitna when money comes in": "Batao paise kab aate hain", "So today's number lasts until then": "Taaki aaj ka number tab tak chale",
    "Match Kitna with your bank": "Kitna ko bank se milao", "One tap, after your first bank message arrives": "Pehla bank message aate hi, ek tap",
    "Your bank balance is ready to match": "Bank balance milane ke liye taiyaar", "Like \"Dinner Friday ₹2,000\", so it's kept aside": "Jaise \"Friday dinner ₹2,000\", taaki alag rakha jaye",
    "spent": "kharch",
    // safe-to-spend breakdown (from the server)
    "Money you have": "Aapke paas", "Money you have (not yet matched with your bank)": "Aapke paas (bank se abhi milaya nahi)",
    "Sure money coming before then": "Pakka aane wale paise", "Your plans": "Aapke plans", "Goal top-ups this month": "Is mahine goals ke liye",
    "Money you owe friends": "Doston ko dene hain", "Safety cushion (kept aside)": "Emergency ke liye alag",
    "You've spent today's safe amount. Whatever you don't spend tomorrow carries forward.": "Aaj ka safe amount kharch ho gaya. Kal jo bachega woh aage judega.",
    "Bills, plans and your cushion need everything you have until your next money. Only spend on essentials.": "Agle paise aane tak bills, plans aur cushion ke liye sab chahiye. Sirf zaroori kharcha karo.",
    "Add your money in (salary, pocket money) or confirm your bank balance, and Kitna works out today's number.": "Aane wale paise (salary, pocket money) jodo ya bank balance batao, Kitna aaj ka number nikal dega.",
    // add / plan / friends modals
    "Add transaction": "Payment jodo", "Edit transaction": "Payment badlo", "Split with friends": "Doston mein baanto", "Split": "Baanto",
    "Money going out": "Jaane wale paise", "Money coming in": "Aane wale paise", "What for": "Kis liye", "When": "Kab",
    "I'm sure this money will come": "Yeh paise pakka aayenge", "Edit plan": "Plan badlo",
    "Plan added. Today's number now keeps it aside.": "Plan jud gaya. Aaj ka number ise alag rakhta hai.", "Plan updated.": "Plan badal gaya.",
    "Who was it with?": "Kiske saath tha?", "I'm paying a share too": "Mera hissa bhi hai",
    "When they pay you back on UPI, Kitna ticks them off by itself.": "Jab woh UPI pe lautayenge, Kitna khud list se hata dega.",
    "Friends' shares are more than you paid.": "Doston ka hissa aapke diye se zyada hai.",
    "They owe me": "Mujhe lene hain", "I owe them": "Mujhe dene hain", "Add money with a friend": "Dost ke saath hisaab jodo",
    "Friend's name": "Dost ka naam", "What for (optional)": "Kis liye (optional)",
    "Money you owe is kept aside in today's number. Money friends owe you is only counted once it arrives.": "Jo dena hai woh aaj ke number mein alag rakha hai. Jo lena hai woh aane ke baad hi gina jayega.",
    // Friends screen
    "Money you lent or borrowed. Ticked off by itself when the UPI payment arrives.": "Diye ya liye paise. UPI payment aate hi khud tick ho jata hai.",
    "Friends owe you": "Doston se lene hain", "You owe friends": "Doston ko dene hain",
    "Not counted in today's number until it arrives.": "Aane tak aaj ke number mein nahi gina.", "Already kept aside in today's number.": "Aaj ke number mein pehle se alag rakha hai.",
    "Split a payment to start.": "Shuru karne ke liye koi payment baanto.", "Nothing to pay back.": "Kuch lautana nahi hai.",
    "Split a payment": "Payment baanto", "Someone owes me": "Kisi se lene hain", "I owe someone": "Kisi ko dene hain",
    "Remind": "Yaad dilao", "They paid": "Unhone de diye", "I paid": "Maine de diye", "Still open": "Abhi baaki",
    "All square": "Sab barabar", "Paid for dinner or a cab? Split it here, or from the payment in Activity.": "Dinner ya cab ka pay kiya? Yahan baanto, ya Hisaab mein us payment se.",
    "Add your UPI ID": "Apna UPI ID jodo", "Reminders you send will include it, so friends can pay in one go.": "Reminder message mein UPI ID jayega, dost turant bhej payenge.",
    "Yes, tick it off": "Haan, tick karo", "Which payment?": "Kaunsa payment?", "Remove this?": "Ise hatayein?",
    "No payments yet to split. Add the expense first.": "Baantne ke liye koi payment nahi. Pehle kharcha jodo.",
    // Plans
    "Coming up": "Aane wala", "Kept aside": "Alag rakha", "Coming in": "Aa raha hai", "Maybe (not counted)": "Shayad (gina nahi)",
    "Mark done": "Ho gaya mark karo", "Marked done.": "Ho gaya.", "No plans yet": "Abhi koi plan nahi", "Past and done": "Pichle aur pure",
    "Your money setup": "Aapka money setup", "When does your money come in?": "Paise kab aate hain?",
    "Same date every month": "Har mahine same tareekh", "It varies": "Fix nahi hai", "Safety cushion (₹)": "Emergency cushion (₹)",
    "Money Kitna never counts as spendable. For emergencies.": "Yeh paise Kitna kabhi kharche mein nahi ginta. Emergency ke liye.",
    "Saved. Today's number is updated.": "Save ho gaya. Aaj ka number update ho gaya.",
    "Tell Kitna what's coming, so today's number is real. Tap a plan to edit it.": "Kitna ko batao kya aane wala hai, taaki aaj ka number sahi ho. Badalne ke liye plan pe tap karo.",
    // Activity
    "Transactions": "Hisaab", "Every rupee in and out.": "Har rupaya, aaya ya gaya.", "All": "Sab", "Expenses": "Kharche",
    "Load more": "Aur dikhao", "No transactions found": "Koi payment nahi mila", "Try different filters, or add one.": "Filter badlo, ya naya jodo.",
    "All categories": "Saari categories", "Search": "Dhoondo",
    // reminders inbox
    "Nothing yet": "Abhi kuch nahi", "Reminders about bills, late refunds and friends show up here.": "Bills, late refund aur doston ke reminders yahan dikhenge.",
    "Get these on your phone →": "Yeh phone pe paao →",
  };

  // Sentences with numbers or names in them: [pattern, replacement].
  const P = [
    [/^Good (morning|afternoon|evening), (.+)$/, (m, part, n) => ({ morning: "Good morning", afternoon: "Namaste", evening: "Good evening" }[part]) + ", " + n],
    [/^Until (\d+ \w+), your next payday\.(.*)$/, (m, d, rest) => `${d} tak, agle payday tak.` + aside(rest)],
    [/^Until (\d+ \w+), the end of the month\.(.*)$/, (m, d, rest) => `${d} tak, mahine ke end tak.` + aside(rest)],
    [/^Spend up to (₹[\d,]+) more today and you're fine until (\d+ \w+)\.(.*)$/, (m, a, d, rest) => `Aaj ${a} aur kharch kar sakte ho, ${d} tak sab theek rahega.` + rest.replace(" Over budget:", " Budget se upar:")],
    [/^÷ (\d+) days? until (\d+ \w+)$/, (m, n, d) => `÷ ${n} din, ${d} tak`],
    [/^(₹[\d,]+) a day$/, (m, a) => `${a} roz`],
    [/^Bills due \((\d+)\)$/, (m, n) => `Bills (${n})`],
    [/^Coming up before (.+)$/, (m, d) => `${d} se pehle`],
    [/^Last 30 days · about (₹[\d,]+) a day$/, (m, a) => `Pichle 30 din · roz lagbhag ${a}`],
    [/^(\d+) of (\d+) done$/, (m, a, b) => `${b} mein se ${a} ho gaye`],
    [/^Your plan · (.+)$/, (m, d) => `Aapka plan · ${d}`],
    [/^About (₹[\d,]+) a day$/, (m, a) => `Roz lagbhag ${a}`],
    [/^Friends owe you (₹[\d,]+)\. Counted once it arrives →$/, (m, a) => `Doston se ${a} lene hain. Aane par gina jayega →`],
    [/^If the money you're not sure about arrives: about (₹[\d,]+) more a day\.$/, (m, a) => `Jo paise pakke nahi, agar aa gaye: roz lagbhag ${a} aur.`],
    [/^Was the (₹[\d,]+) (today|yesterday|on .+) from (.+)\?$/, (m, a, d, n) => `${d === "today" ? "Aaj" : d === "yesterday" ? "Kal" : d.slice(3)} ke ${a} kya ${n} ne bheje?`],
    [/^Your share: (₹[\d,.]+) \(only this counts as your spending\)\.$/, (m, a) => `Aapka hissa: ${a} (sirf yahi aapka kharcha gina jayega).`],
    [/^Done\. Friends owe you (₹[\d,.]+) in total\.$/, (m, a) => `Ho gaya. Doston se kul ${a} lene hain.`],
    [/^(.+) is ticked off\.$/, (m, n) => `${n} list se hat gaya.`],
    [/^Saved (₹[\d,.]+) (expense|income)\.(.*)$/, (m, a, k, rest) => `${a} ${k === "expense" ? "kharcha" : "aamdani"} save ho gaya.` + rest],
    [/^Paid back \((\d+)\)$/, (m, n) => `Lauta diye (${n})`],
    [/^(\d+) new payments? added from Gmail\.$/, (m, n) => `Gmail se ${n} naye payment jude.`],
  ];
  function aside(rest) { return rest.replace(" Bills and plans are already kept aside.", " Bills aur plans pehle se alag rakhe hain."); }

  function translate(text) {
    const t = text.trim();
    if (!t || t.length > 300) return null;
    let out = D[t];
    if (out === undefined) {
      for (const [re, fn] of P) { const m = t.match(re); if (m) { out = fn(...m); break; } }
    }
    if (out === undefined || out === t) return null;
    return text.replace(t, out);
  }

  const SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, INPUT: 1, CODE: 1, PRE: 1 };
  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { const r = translate(root.nodeValue); if (r !== null) root.nodeValue = r; return; }
    if (root.nodeType !== 1 || SKIP[root.tagName] || root.closest && root.closest("[data-no-tr]")) return;
    for (const a of ["placeholder", "aria-label", "title"]) {
      const v = root.getAttribute && root.getAttribute(a);
      if (v) { const r = translate(v); if (r !== null) root.setAttribute(a, r); }
    }
    const it = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let n = it.nextNode();
    while (n) {
      if (n.nodeType === 3) {
        const p = n.parentNode;
        if (p && !SKIP[p.tagName]) { const r = translate(n.nodeValue); if (r !== null) n.nodeValue = r; }
      } else {
        for (const a of ["placeholder", "aria-label", "title"]) {
          const v = n.getAttribute(a);
          if (v) { const r = translate(v); if (r !== null) n.setAttribute(a, r); }
        }
      }
      n = it.nextNode();
    }
  }

  let on = false;
  window.FluxI18n = {
    translate,
    get on() { return on; },
    start(lang) {
      if (lang !== "hinglish" || on) return;
      on = true;
      document.documentElement.lang = "hi-Latn";
      walk(document.body);
      new MutationObserver((muts) => {
        for (const m of muts) {
          if (m.type === "characterData") { const r = translate(m.target.nodeValue); if (r !== null) m.target.nodeValue = r; }
          else m.addedNodes.forEach(walk);
        }
      }).observe(document.body, { childList: true, subtree: true, characterData: true });
    },
  };
})();
