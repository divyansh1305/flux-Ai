"""Merchant → category, with a confidence score and the reason.

Order of evidence (strongest first):
  1. Merchant Category Code (from UPI QR codes)           confidence 0.90
  2. Known merchant keyword (Swiggy, Uber, Netflix…)       confidence 0.95
  3. Generic keyword (restaurant, pharmacy, rent…)          confidence 0.70
  4. Nothing matched                                        confidence 0.20 ("Other")
Low-confidence results should be shown to the user to confirm.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

EXPENSE_CATEGORIES = [
    "Food & Dining", "Groceries", "Transport", "Travel", "Shopping", "Subscriptions", "Bills & Utilities", "Rent",
    "Entertainment", "Health", "Education", "Personal Care", "Investments", "Transfers", "Other",
]
INCOME_CATEGORIES = ["Salary", "Freelance", "Pocket Money", "Refund", "Cashback", "Interest", "Investment Returns",
                     "Gift", "Other Income"]

# (category, brand keywords [strong], generic keywords [weaker])
EXPENSE_RULES = [
    ("Subscriptions", ["netflix", "spotify", "hotstar", "prime video", "amazon prime", "youtube premium", "youtube",
                       "jiocinema", "jiohotstar", "sonyliv", "zee5", "apple.com", "apple services", "google play",
                       "icloud", "chatgpt", "openai", "notion", "linkedin", "adobe", "canva", "audible", "gaana",
                       "wynk", "disney"], ["subscription", "membership renewal", "autopay"]),
    ("Food & Dining", ["swiggy", "zomato", "dominos", "domino", "kfc", "mcdonald", "burger king", "starbucks",
                       "chaayos", "chai point", "third wave", "blue tokai", "eatsure", "box8", "faasos", "haldiram",
                       "subway", "pizza hut", "barbeque nation", "wow momo", "behrouz", "rebel foods", "magicpin",
                       "dunzo daily"], ["restaurant", "cafe", "coffee", "dhaba", "canteen", "mess", "biryani", "food",
                                         "pizza", "bakery", "sweets", "tea stall", "juice", "eatery", "kitchen"]),
    ("Groceries", ["blinkit", "zepto", "bigbasket", "instamart", "dmart", "d-mart", "reliance fresh", "jiomart",
                   "grofers", "more retail", "milkbasket", "country delight", "spencer", "nature basket", "swiggy instamart",
                   "bb daily", "licious", "freshtohome"], ["grocery", "groceries", "kirana", "supermarket", "vegetable",
                                                          "fruits", "dairy", "provision", "general store", "mart"]),
    ("Transport", ["uber", "ola", "rapido", "namma yatri", "blusmart", "dmrc", "irctc", "redbus", "fastag", "hpcl",
                   "bpcl", "indian oil", "iocl", "shell", "nayara", "yulu", "bounce", "metro card"],
     ["metro", "petrol", "fuel", "diesel", "parking", "toll", "cab", "taxi", "auto rickshaw", "bus pass"]),
    ("Travel", ["makemytrip", "goibibo", "cleartrip", "indigo", "air india", "vistara", "akasa", "spicejet", "oyo",
                "airbnb", "booking.com", "ixigo", "yatra", "easemytrip", "agoda", "treebo", "fabhotels", "zostel"],
     ["hotel", "flight", "airlines", "resort", "hostel booking", "travels"]),
    ("Shopping", ["amazon", "flipkart", "myntra", "ajio", "meesho", "nykaa", "tatacliq", "tata cliq", "croma",
                  "reliance digital", "decathlon", "ikea", "lenskart", "snapdeal", "shoppers stop", "westside",
                  "zara", "h&m", "max fashion", "uniqlo", "pantaloons", "lifestyle", "boat", "vijay sales", "firstcry",
                  "bewakoof", "souled store", "apple store", "samsung"], ["shopping", "store", "retail", "fashion",
                                                                          "electronics", "mobile shop", "garments"]),
    ("Bills & Utilities", ["airtel", "jio", "vodafone", "bsnl", "tata power", "adani electricity", "bescom", "msedcl",
                           "uhbvn", "dhbvn", "tneb", "kseb", "bses", "indane", "bharat gas", "hp gas", "act fibernet",
                           "hathway", "tata play", "dish tv", "billdesk", "mahanagar gas", "igl"],
     ["electricity", "water bill", "gas bill", "broadband", "recharge", "dth", "bill payment", "postpaid", "prepaid",
      "wifi", "maintenance"]),
    ("Rent", ["nobroker", "nestaway", "housing.com", "stanza living", "zolo"], ["rent", "landlord", "pg rent",
                                                                                 "house rent", "room rent", "hostel fee"]),
    ("Entertainment", ["bookmyshow", "pvr", "inox", "cinepolis", "steam", "playstation", "xbox", "dream11",
                       "district", "paytm insider", "mpl", "winzo"], ["movie", "cinema", "gaming", "concert", "event",
                                                                     "amusement", "club"]),
    ("Health", ["apollo", "medplus", "netmeds", "1mg", "tata 1mg", "pharmeasy", "practo", "cult.fit", "cultfit",
                "healthifyme", "thyrocare", "lal path", "max hospital", "fortis", "aiims"],
     ["pharmacy", "chemist", "medical", "hospital", "clinic", "doctor", "diagnostic", "lab", "dental", "gym",
      "fitness", "medicine"]),
    ("Education", ["udemy", "coursera", "unacademy", "byju", "physics wallah", "physicswallah", "upgrad", "leetcode",
                   "geeksforgeeks", "scaler", "simplilearn", "vedantu", "chegg", "duolingo"],
     ["college", "university", "school", "tuition", "coaching", "exam fee", "fees", "stationery", "books",
      "library"]),
    ("Personal Care", ["urban company", "urbanclap", "lakme", "naturals", "looks salon", "jawed habib"],
     ["salon", "barber", "spa", "parlour", "grooming", "haircut"]),
    ("Investments", ["zerodha", "groww", "upstox", "coin by zerodha", "kuvera", "paytm money", "smallcase", "indmoney",
                     "angel one", "dhan", "et money", "nps trust", "ppf"], ["mutual fund", "sip", "stocks", "demat",
                                                                             "recurring deposit", "fixed deposit"]),
    ("Transfers", ["cred"], ["atm", "atw", "nwd", "atm wdl", "cash withdrawal", "self transfer", "to self", "own account", "credit card payment",
                             "cc payment", "card payment", "wallet load", "add money"]),
]

INCOME_RULES = [
    ("Cashback", [], ["cashback", "cash back", "reward credited", "scratch card", "rewards"]),
    ("Refund", [], ["refund", "reversal", "reversed", "chargeback", "returned"]),
    ("Salary", [], ["salary", "sal for", "payroll", "stipend", "wages"]),
    ("Interest", [], ["interest", "int.pd", "int pd", "int cr", "int credit", "savings int"]),
    ("Investment Returns", ["zerodha", "groww", "upstox", "coin"], ["dividend", "redemption", "mf redeem"]),
    ("Freelance", ["upwork", "fiverr", "toptal", "razorpay payout"], ["freelance", "invoice", "consulting",
                                                                      "professional fee"]),
    ("Pocket Money", [], ["papa", "mummy", "mom", "dad", "pocket money", "father", "mother"]),
    ("Gift", [], ["gift", "shagun", "birthday"]),
]

MCC_CATEGORIES = {
    "5811": "Food & Dining", "5812": "Food & Dining", "5813": "Food & Dining", "5814": "Food & Dining",
    "5411": "Groceries", "5422": "Groceries", "5441": "Groceries", "5451": "Groceries", "5462": "Food & Dining",
    "5499": "Groceries", "4111": "Transport", "4121": "Transport", "4131": "Transport", "4784": "Transport",
    "4789": "Transport", "5541": "Transport", "5542": "Transport", "7523": "Transport", "4112": "Travel",
    "4511": "Travel", "4722": "Travel", "7011": "Travel", "5311": "Shopping", "5399": "Shopping", "5651": "Shopping",
    "5661": "Shopping", "5691": "Shopping", "5699": "Shopping", "5732": "Shopping", "5941": "Shopping",
    "5945": "Shopping", "5999": "Shopping", "4814": "Bills & Utilities", "4899": "Bills & Utilities",
    "4900": "Bills & Utilities", "4816": "Subscriptions", "5815": "Subscriptions", "5817": "Subscriptions",
    "5818": "Subscriptions", "5816": "Entertainment", "7832": "Entertainment", "7922": "Entertainment",
    "7996": "Entertainment", "7999": "Entertainment", "5912": "Health", "8011": "Health", "8021": "Health",
    "8062": "Health", "8071": "Health", "8099": "Health", "7997": "Health", "8211": "Education", "8220": "Education",
    "8299": "Education", "5942": "Education", "5943": "Education", "7230": "Personal Care", "7298": "Personal Care",
    "6513": "Rent", "6211": "Investments",
}


def _norm(text: str) -> str:
    low = (text or "").lower()
    keep = " " + re.sub(r"[^a-z0-9.&]+", " ", low) + " "
    # Also add a dot-free copy so "ola.money" or "swiggy.instamart" match "ola" / "instamart".
    return keep + re.sub(r"[^a-z0-9&]+", " ", low) + " "


def _hit(text: str, word: str) -> bool:
    w = word.strip().lower()
    # Short words ("ola", "jio", "sip") must match a whole word, never part of one.
    if len(w) <= 4:
        return f" {w} " in text
    if w in text:
        return True
    # UPI handles glue words together: "tatapower@hdfcbank", "urbancompany@ybl".
    if " " in w:
        squashed = w.replace(" ", "")
        return any(tok.startswith(squashed) for tok in text.split())
    return False


# UPI handles / statement codes -> the brand people recognise.
BRAND_ALIASES = {
    "iocl": "Indian Oil", "indianoil": "Indian Oil", "olacabs": "Ola", "ola cabs": "Ola", "pvrcinemas": "PVR",
    "pvr inox": "PVR INOX", "bms": "BookMyShow", "bookmyshow": "BookMyShow", "apollopharmacy": "Apollo Pharmacy",
    "tatapower": "Tata Power", "chaipoint": "Chai Point", "urbancompany": "Urban Company", "makemytrip": "MakeMyTrip",
    "bigbasket": "BigBasket", "dmart": "DMart", "avenue supermarts": "DMart", "bundl technologies": "Swiggy",
    "zomato media": "Zomato", "uber india": "Uber", "uber india systems": "Uber", "ani technologies": "Ola",
    "roppen transportation": "Rapido", "one97": "Paytm", "cultfit": "Cult.fit", "irctc": "IRCTC", "kfc": "KFC",
    "oyo": "OYO", "phonepe": "PhonePe", "ola money": "Ola", "olamoney": "Ola", "bundl technologies": "Swiggy",
    "swiggy instamart": "Swiggy", "rapido bike": "Rapido", "zerodha coin": "Zerodha", "zerodha broking": "Zerodha",
    "airtel payments": "Airtel", "decathlon sports": "Decathlon", "amazon pay india": "Amazon", "amazon pay": "Amazon", "flipkart internet": "Flipkart",
}


def brand_name(name: str) -> str:
    key = (name or "").strip().lower()
    return BRAND_ALIASES.get(key) or BRAND_ALIASES.get(key.replace(" ", "")) or name


def categorize(text: str, direction: str = "debit", mcc: Optional[str] = None) -> Tuple[str, float, str]:
    """Return (category, confidence 0–1, human-readable reason)."""
    t = _norm(text)
    if direction == "credit":
        for cat, brands, generic in INCOME_RULES:
            for w in brands + generic:
                if _hit(t, w):
                    return cat, 0.9, f"matched “{w}”"
        return "Other Income", 0.2, "no rule matched"
    if mcc and mcc in MCC_CATEGORIES:
        return MCC_CATEGORIES[mcc], 0.9, f"merchant category code {mcc}"
    # The most specific brand wins: "swiggy instamart" (Groceries) beats "swiggy" (Food).
    best = None
    for cat, brands, _generic in EXPENSE_RULES:
        for w in brands:
            if _hit(t, w) and (best is None or len(w) > len(best[1])):
                best = (cat, w)
    if best:
        return best[0], 0.95, f"known merchant “{best[1]}”"
    for cat, _brands, generic in EXPENSE_RULES:
        for w in generic:
            if _hit(t, w):
                return cat, 0.7, f"keyword “{w}”"
    return "Other", 0.2, "no rule matched"
