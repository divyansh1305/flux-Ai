"""Instruments Flux lets beginners invest goal savings into, plus a cached price lookup.

Deliberately a short, boring list: broad index and gold ETFs. Flux is not a
stock-tips app; it helps people put savings to work in diversified funds.
"""
import logging
import threading
import time

log = logging.getLogger("flux.market")

INSTRUMENTS = [
    {"symbol": "NIFTYBEES", "name": "Nifty 50 ETF", "what": "India's 50 largest companies in one unit.", "risk": "Medium",
     "horizon": "5+ years"},
    {"symbol": "JUNIORBEES", "name": "Nifty Next 50 ETF", "what": "The next 50 large companies after the Nifty 50.",
     "risk": "Medium-high", "horizon": "5+ years"},
    {"symbol": "GOLDBEES", "name": "Gold ETF", "what": "Tracks the price of gold. Good for diversifying.",
     "risk": "Medium", "horizon": "3+ years"},
    {"symbol": "LIQUIDBEES", "name": "Liquid ETF", "what": "Very low-risk, cash-like. Good for short-term goals.",
     "risk": "Low", "horizon": "Any"},
]
SYMBOLS = {i["symbol"] for i in INSTRUMENTS}

_cache = {}
_lock = threading.Lock()
TTL = 300  # seconds


def fetch_price(symbol):
    """Last traded price in rupees from Yahoo Finance (unofficial, best-effort). None if unavailable."""
    import requests

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS?interval=1d&range=1d"
    try:
        r = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0 Flux"})
        r.raise_for_status()
        meta = r.json()["chart"]["result"][0]["meta"]
        price = float(meta.get("regularMarketPrice") or meta.get("previousClose"))
        return price if price > 0 else None
    except Exception as e:  # network down, blocked, format change…
        log.info("Price lookup failed for %s: %s", symbol, e)
        return None


def price(symbol, fetcher=None):
    if symbol not in SYMBOLS:
        return None
    now = time.time()
    with _lock:
        hit = _cache.get(symbol)
        if hit and now - hit[1] < TTL:
            return hit[0]
    value = (fetcher or fetch_price)(symbol)
    if value:
        with _lock:
            _cache[symbol] = (value, now)
    return value


def clear_cache():
    with _lock:
        _cache.clear()
