"""Voice command understanding (English, Hindi and Hinglish).

parse(text) turns what the user said into a structured command:
    {"intent": "add_expense", "amount": 250.0, "category": "Food & Dining", "note": "swiggy", ...}

It is rule-based first (instant, offline, predictable). Anything it can't
understand goes to Gemini, whose answer is validated against the same
whitelist of intents, so the AI can never trigger an unknown action.
"""
import re
from datetime import timedelta

from .categorize import categorize
from .finance import EXPENSE_CATEGORIES, INCOME_CATEGORIES
from . import clock

INTENTS = {
    "add_expense", "add_income", "check_balance", "spending_query", "budget_status", "set_budget",
    "goal_status", "create_goal", "add_to_goal", "can_i_afford", "health_score", "forecast", "pay", "safe_to_spend",
    "bills",
    "undo", "navigate", "logout", "help", "ask_coach", "unknown",
}
PAGES = {
    "dashboard": "/app", "home": "/app", "transactions": "/app/transactions", "history": "/app/transactions",
    "budgets": "/app/budgets", "budget": "/app/budgets", "goals": "/app/goals", "goal": "/app/goals",
    "import": "/app/import", "statement": "/app/import", "coach": "/app/coach", "insights": "/app/coach",
    "report": "/app/coach", "settings": "/app/settings", "profile": "/app/settings",
    "pay": "/app/pay", "scanner": "/app/pay", "invest": "/app/invest", "investments": "/app/invest",
    "portfolio": "/app/invest", "sms": "/app/share",
}

# Devanagari -> Hinglish so one rule set handles both scripts.
DEVANAGARI = {
    "मैंने": "maine", "मैने": "maine", "रुपये": "rupaye", "रुपए": "rupaye", "रुपया": "rupaye", "रूपए": "rupaye",
    "खर्च": "kharch", "खर्चा": "kharcha", "किए": "kiye", "किया": "kiya", "कीजिए": "karo", "करो": "karo",
    "खाने": "khane", "खाना": "khana", "चाय": "chai", "कॉफी": "coffee", "पेट्रोल": "petrol", "किराया": "kiraya",
    "दवाई": "dawai", "दवा": "dawai", "कपड़े": "kapde", "सब्जी": "sabzi", "राशन": "ration", "मूवी": "movie",
    "सैलरी": "salary", "तनख्वाह": "salary", "कमाए": "kamaye", "मिले": "mile", "मिला": "mila", "पापा": "papa",
    "मम्मी": "mummy", "बैलेंस": "balance", "बचे": "bache", "बचा": "bacha", "कितने": "kitne", "कितना": "kitna",
    "पैसे": "paise", "पैसा": "paisa", "है": "hai", "हैं": "hain", "आज": "aaj", "कल": "kal", "महीने": "mahine",
    "महीना": "mahina", "इस": "is", "हफ्ते": "hafte", "बजट": "budget", "लक्ष्य": "goal", "गोल": "goal",
    "बनाओ": "banao", "जोड़ो": "jodo", "डालो": "daalo", "पर": "par", "पे": "pe", "के": "ke", "का": "ka", "की": "ki",
    "लिए": "liye", "में": "mein", "सौ": "sau", "हजार": "hazaar", "हज़ार": "hazaar", "लाख": "lakh",
    "खोलो": "kholo", "दिखाओ": "dikhao", "स्कोर": "score", "वापस": "undo", "हटाओ": "hatao",
    "क्या": "kya", "मैं": "main", "खरीद": "kharid", "सकता": "sakta", "सकती": "sakti", "लेना": "lena",
}

NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    # Hindi
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6, "saat": 7,
    "aath": 8, "nau": 9, "das": 10, "bees": 20, "tees": 30, "chalees": 40, "pachaas": 50, "pachas": 50,
    "saath": 60, "sattar": 70, "assi": 80, "nabbe": 90, "dedh": 1.5, "dhai": 2.5, "dhaai": 2.5,
}
HINDI_SMALL = {"ek", "do", "teen", "char", "chaar", "paanch", "panch", "chhe", "che", "saat", "aath", "nau", "das",
               "bees", "tees", "chalees", "pachaas", "pachas", "saath", "sattar", "assi", "nabbe", "dedh", "dhai", "dhaai"}
MULTIPLIERS = {"hundred": 100, "sau": 100, "thousand": 1000, "hazaar": 1000, "hazar": 1000, "hajar": 1000,
               "k": 1000, "lakh": 100000, "lac": 100000, "lakhs": 100000}

CATEGORY_WORDS = {
    "Food & Dining": ["food", "lunch", "dinner", "breakfast", "snacks", "khana", "khane", "chai", "coffee", "tea",
                      "restaurant", "eating", "maggi", "momos", "pizza", "burger"],
    "Groceries": ["grocery", "groceries", "sabzi", "vegetables", "ration", "milk", "doodh", "fruits"],
    "Transport": ["petrol", "diesel", "cab", "taxi", "auto", "bus", "train", "metro", "travel to", "fuel", "rickshaw"],
    "Shopping": ["shopping", "clothes", "kapde", "shoes", "shirt", "jeans", "headphones", "phone", "watch"],
    "Bills & Utilities": ["bill", "recharge", "electricity", "bijli", "wifi", "internet", "mobile bill"],
    "Rent": ["rent", "kiraya", "pg"],
    "Entertainment": ["movie", "movies", "film", "game", "games", "party", "outing"],
    "Health": ["medicine", "medicines", "dawai", "doctor", "hospital", "gym"],
    "Education": ["books", "book", "fees", "course", "college", "notes", "stationery"],
    "Subscriptions": ["subscription", "netflix", "spotify", "prime", "hotstar"],
    "Travel": ["trip", "flight", "hotel", "vacation"],
    "Personal Care": ["haircut", "salon", "parlour"],
}
INCOME_WORDS = {
    "Salary": ["salary", "stipend", "paycheck"],
    "Freelance": ["freelance", "client", "project payment", "gig"],
    "Pocket Money": ["pocket money", "papa", "mummy", "mom", "dad", "parents", "ghar se"],
    "Gift": ["gift", "birthday", "shagun"],
    "Refund": ["refund", "cashback", "returned"],
    "Interest": ["interest"],
}

FILLER = {"i", "a", "an", "the", "on", "for", "to", "at", "of", "my", "me", "rs", "rupees", "rupee", "rupaye",
          "inr", "spent", "spend", "paid", "pay", "bought", "buy", "add", "expense", "kharch", "kharcha", "kiye",
          "kiya", "maine", "par", "pe", "ke", "ka", "ki", "liye", "mein", "hai", "today", "aaj", "yesterday", "kal",
          "please", "flux", "hey", "log", "record", "and", "just", "worth", "karo"}


def normalise(text):
    t = text.strip()
    for dev, lat in DEVANAGARI.items():
        t = t.replace(dev, f" {lat} ")
    t = t.lower().replace("₹", " rs ").replace(",", "")
    t = re.sub(r"(\d)\s*k\b", lambda m: m.group(1) + "000", t)  # "5k" -> "5000"
    t = re.sub(r"[^\w\s.@]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def extract_amount(t):
    """Find the money amount in normalised text. Returns (amount, text_without_amount)."""
    # Digits, optionally followed by a multiplier word: "2 lakh", "1.5 thousand", "500"
    m = re.search(r"(\d+(?:\.\d+)?)\s*(hundred|sau|thousand|hazaar|hazar|hajar|lakh|lakhs|lac)?\b", t)
    if m:
        value = float(m.group(1)) * (MULTIPLIERS.get(m.group(2), 1) if m.group(2) else 1)
        return value, (t[:m.start()] + " " + t[m.end():]).strip()
    # Words: "two hundred fifty", "paanch sau", "dedh hazaar"
    tokens = t.split()
    total, current, used, started = 0.0, 0.0, [], False
    for i, tok in enumerate(tokens):
        if tok in NUM_WORDS:
            # Hindi number words ("do", "das", "saath") are also ordinary words, so they only
            # count as numbers when followed by sau/hazaar/lakh ("do sau", "paanch hazaar").
            if tok in HINDI_SMALL and not (i + 1 < len(tokens) and tokens[i + 1] in MULTIPLIERS):
                if started:
                    break
                continue
            current += NUM_WORDS[tok]
            used.append(i)
            started = True
        elif tok in MULTIPLIERS and tok != "k" and started:
            mult = MULTIPLIERS[tok]
            if mult == 100:
                current = (current or 1) * 100
            else:
                total += (current or 1) * mult
                current = 0
            used.append(i)
        elif tok == "and" and started:
            used.append(i)
        elif started:
            break
    value = total + current
    if value > 0 and started:
        rest = " ".join(tok for i, tok in enumerate(tokens) if i not in used)
        return value, rest
    return None, t


def guess_category(text, kind):
    words = INCOME_WORDS if kind == "income" else CATEGORY_WORDS
    padded = f" {text} "
    for cat, keys in words.items():
        if any(f" {k} " in padded for k in keys):
            return cat
    cat, kw = categorize(text, kind)
    return cat


def _note(text):
    words = [w for w in text.split() if w not in FILLER and not w.isdigit()]
    return " ".join(words)[:60].strip().capitalize()


def _period(t):
    today = clock.today()
    if re.search(r"\b(today|aaj)\b", t):
        return "today", today, today
    if re.search(r"\b(yesterday)\b", t) or re.search(r"\bkal\b", t):
        y = today - timedelta(days=1)
        return "yesterday", y, y
    if re.search(r"\b(week|hafte|hafta)\b", t):
        return "this week", today - timedelta(days=today.weekday()), today
    if re.search(r"\blast month\b|\bpichle mahine\b", t):
        first = today.replace(day=1)
        last = first - timedelta(days=1)
        return "last month", last.replace(day=1), last
    return "this month", today.replace(day=1), today


def _day_of(t):
    if re.search(r"\b(yesterday|kal)\b", t):
        return (clock.today() - timedelta(days=1)).isoformat()
    return clock.today().isoformat()


def _has(t, *patterns):
    return any(re.search(p, t) for p in patterns)


def parse(text):
    raw = (text or "").strip()
    t = normalise(raw)
    if not t:
        return {"intent": "unknown"}

    # Undo / help / logout / navigation
    if _has(t, r"^(undo|cancel that|delete (the )?last|remove (the )?last|wapas|undo karo|hatao)\b", r"\bundo\b"):
        return {"intent": "undo"}
    if _has(t, r"\bwhat can you do\b", r"^help\b", r"\bkya kar sakte\b", r"\bcommands\b"):
        return {"intent": "help"}
    if _has(t, r"\b(log ?out|sign ?out)\b"):
        return {"intent": "logout"}
    nav = re.search(r"\b(open|go to|show me|show|take me to|kholo|dikhao)\b\s*(?:the |my )?(\w+)", t)
    if nav and nav.group(2) in PAGES and not _has(t, r"\bhow much\b", r"\bkitna\b"):
        return {"intent": "navigate", "page": PAGES[nav.group(2)], "page_name": nav.group(2)}
    m = re.match(r"^(\w+)( page)?$", t)
    if m and m.group(1) in PAGES:
        return {"intent": "navigate", "page": PAGES[m.group(1)], "page_name": m.group(1)}

    if _has(t, r"^(scan|scan and pay|scan karo|qr|scan qr|open scanner)\b"):
        return {"intent": "navigate", "page": "/app/pay", "page_name": "Scan & Pay"}

    amount, rest = extract_amount(t)

    # Paying someone: "pay 200 to rahul", "send 500 to riya@okaxis", "rahul ko 200 bhejo"
    if amount and _has(t, r"^(pay|send|transfer)\b", r"\b(bhejo|bhej do|pay karo|de do)\b"):
        vpa = re.search(r"[a-z0-9.\-_]{2,}@[a-z][a-z0-9.]{2,}", t)
        payee = re.sub(r"\b(pay|send|transfer|to|rs|rupees|rupaye|ko|bhejo|bhej|do|karo|de|please)\b", " ", rest)
        return {"intent": "pay", "amount": amount, "vpa": vpa.group(0) if vpa else None,
                "payee": re.sub(r"\s+", " ", payee).strip()[:60]}

    # Budgets: "set food budget to 5000"
    if "budget" in t and amount and _has(t, r"\b(set|make|change|update|rakho|banao|fix)\b"):
        cat = guess_category(rest.replace("budget", " "), "expense")
        return {"intent": "set_budget", "amount": amount, "category": cat}
    if "budget" in t:
        cat = guess_category(t.replace("budget", " "), "expense")
        return {"intent": "budget_status", "category": None if cat == "Other" else cat}

    # Goals
    if "goal" in t or _has(t, r"\bsave (for|towards)\b", r"\bsaving for\b"):
        if _has(t, r"\b(create|new|make|start|banao|set up|add a)\b") and amount:
            title = re.sub(r"\b(create|new|make|start|banao|set up|add|a|goal|called|named|for|of|rs|rupees|rupaye|target|ka|ki|ke|liye)\b", " ", rest)
            title = re.sub(r"\s+", " ", title).strip().title() or "New Goal"
            return {"intent": "create_goal", "amount": amount, "title": title[:60]}
        if amount and _has(t, r"\b(add|put|save|move|transfer|daalo|jodo|deposit)\b"):
            name = re.sub(r"\b(add|put|save|move|transfer|daalo|jodo|deposit|to|into|in|my|the|goal|for|towards|rs|rupees|rupaye|mein|me)\b", " ", rest)
            return {"intent": "add_to_goal", "amount": amount, "goal": re.sub(r"\s+", " ", name).strip()}
        name = re.sub(r"\b(how|is|my|the|goal|goals|doing|status|progress|of|kaisa|chal|raha|hai|show|what|s)\b", " ", t)
        return {"intent": "goal_status", "goal": re.sub(r"\s+", " ", name).strip() or None}

    # Affordability: "can I afford 3000 shoes", "kya main 2000 ke headphones le sakta hoon"
    if amount and _has(t, r"\b(afford|should i (buy|spend|get)|can i (buy|spend|get)|le sakta|le sakti|kharid sakta|kharid sakti|lu kya|lena chahiye)\b"):
        return {"intent": "can_i_afford", "amount": amount, "category": guess_category(rest, "expense"), "note": _note(rest)}

    if _has(t, r"\b(spend|kharch\w*)\b.*\btoday\b|\btoday\b.*\b(spend|kharch\w*)\b|\bsafe to spend\b|"
               r"\baaj kitna\b|\bhow much can i spend\b"):
        if not _has(t, r"\bdid i\b|\bhave i\b|\bkiya\b|\bkiye\b|\bspent\b"):
            return {"intent": "safe_to_spend"}
    if _has(t, r"\b(bills?|subscriptions?|upcoming payments?|recurring)\b") and not amount:
        return {"intent": "bills"}

    # Score / forecast / balance / spending queries
    if _has(t, r"\b(health )?score\b"):
        return {"intent": "health_score"}
    if _has(t, r"\b(forecast|predict|will i spend|end of (the )?month|month end|projection)\b"):
        return {"intent": "forecast"}
    if _has(t, r"\b(balance|how much money (do i have|is left)|kitne paise|kitna paisa|paise bache|bacha hai|bache hain|money left|left with)\b"):
        return {"intent": "check_balance"}
    if _has(t, r"\bhow much (did i|have i|i) (spend|spent)\b", r"\bspending\b", r"\bkitna kharch", r"\bkharcha kitna\b",
            r"\bwhere (did|does) my money go\b", r"\bspent (this|today|on)\b.*\?$"):
        label, start, end = _period(t)
        cat = guess_category(re.sub(r"\b(how|much|did|i|spend|spent|on|this|month|week|today|yesterday|kitna|kharch|kharcha|kiya|is|mahine|hafte|aaj|last|my|spending)\b", " ", t), "expense")
        return {"intent": "spending_query", "period": label, "from": start.isoformat(), "to": end.isoformat(),
                "category": None if cat == "Other" else cat}

    # Income: "got salary 30000", "received 5000 from papa", "papa se 2000 mile"
    if amount and _has(t, r"\b(got|received|earned|income|salary|credited|mile|mila|kamaye|kamaya|stipend|pocket money)\b"):
        return {"intent": "add_income", "amount": amount, "category": guess_category(rest, "income"),
                "note": _note(re.sub(r"\b(got|received|earned|income|credited|mile|mila|kamaye|kamaya|from|se)\b", " ", rest)),
                "date": _day_of(t)}

    # Expense: "spent 250 on swiggy", "200 chai pe", "paid 500 for petrol", or just "300 groceries"
    if amount:
        return {"intent": "add_expense", "amount": amount, "category": guess_category(rest, "expense"),
                "note": _note(rest), "date": _day_of(t)}

    # A question with no amount -> AI coach
    if _has(t, r"\b(why|how|what|should|kya|kaise|kyu|kyun|tips|advice|suggest)\b") or raw.endswith("?"):
        return {"intent": "ask_coach", "question": raw[:500]}
    return {"intent": "unknown", "text": raw[:200]}


AI_PROMPT = """Convert this voice command for a personal-finance app into JSON.
Allowed intents: add_expense, add_income, check_balance, spending_query, budget_status, set_budget,
goal_status, create_goal, add_to_goal, can_i_afford, health_score, forecast, pay, undo, navigate, help, ask_coach, unknown.
Fields: intent, amount (number in rupees, or null), category (one of the lists below or null), note (short text),
title (for create_goal), goal (goal name for add_to_goal/goal_status), page (one of: dashboard, transactions,
budgets, goals, import, coach, settings, pay, invest), question (for ask_coach), payee (for pay).
Expense categories: {exp}
Income categories: {inc}
The command may be English, Hindi or Hinglish. Output JSON only.
Command: {text}"""


def parse_with_ai(text, generate):
    """Use the LLM only to *classify*; the result is validated like any user input."""
    out = generate(AI_PROMPT.format(exp=", ".join(EXPENSE_CATEGORIES), inc=", ".join(INCOME_CATEGORIES),
                                    text=text[:300]), json_mode=True, max_tokens=200)
    if not isinstance(out, dict) or out.get("intent") not in INTENTS:
        return None
    cmd = {"intent": out["intent"]}
    try:
        if out.get("amount") is not None:
            amt = float(out["amount"])
            if 0 < amt <= 10_000_000:
                cmd["amount"] = amt
    except (TypeError, ValueError):
        pass
    kind = "income" if cmd["intent"] == "add_income" else "expense"
    allowed = INCOME_CATEGORIES if kind == "income" else EXPENSE_CATEGORIES
    cmd["category"] = out.get("category") if out.get("category") in allowed else None
    for k in ("note", "title", "goal", "question", "payee"):
        if isinstance(out.get(k), str):
            cmd[k] = out[k][:100]
    if cmd["intent"] == "navigate":
        page = out.get("page")
        if page not in PAGES:
            return None
        cmd.update(page=PAGES[page], page_name=page)
    if cmd["intent"] in {"add_expense", "add_income", "set_budget", "create_goal", "add_to_goal", "can_i_afford", "pay"} \
            and "amount" not in cmd:
        return None
    if cmd["intent"] in {"add_expense", "add_income"}:
        cmd.setdefault("date", clock.today().isoformat())
        if not cmd["category"]:
            cmd["category"] = "Other Income" if kind == "income" else "Other"
    if cmd["intent"] == "spending_query":
        label, start, end = _period(normalise(text))
        cmd.update(period=label, **{"from": start.isoformat(), "to": end.isoformat()})
    if cmd["intent"] == "ask_coach":
        cmd["question"] = text[:500]
    return cmd
