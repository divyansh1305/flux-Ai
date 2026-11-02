"""Local date for the app's users (India by default).

Servers usually run in UTC, so between 6:30 pm and midnight IST `date.today()` on the server is
the wrong day for Indian users. Every business date in Flux
comes from here instead.
"""
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Kolkata"))


def today() -> date:
    return datetime.now(TZ).date()


def now() -> datetime:
    return datetime.now(TZ)
