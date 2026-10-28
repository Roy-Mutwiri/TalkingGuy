"""Which chart is "the chart of the hour".

Rule from the operator: teach on XAU/USD (gold) whenever the forex market is open,
otherwise teach on BTC/USDT. Gold spot trades roughly Sunday 23:00 UTC to Friday 22:00 UTC
with a daily maintenance break 22:00-23:00 UTC (exact times vary by broker by an hour).
"""
from __future__ import annotations

from datetime import datetime, timezone

GOLD = "XAUUSD"
CRYPTO = "BTCUSDT"


def gold_market_open(now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    wd, h = now.weekday(), now.hour  # Monday=0 ... Sunday=6
    if wd == 5:                      # Saturday: closed
        return False
    if wd == 6:                      # Sunday: opens 23:00 UTC
        return h >= 23
    if wd == 4 and h >= 22:          # Friday: closes 22:00 UTC
        return False
    if h == 22:                      # daily break 22:00-23:00 UTC
        return False
    return True


def primary_symbol(now: datetime | None = None) -> str:
    return GOLD if gold_market_open(now) else CRYPTO


def session_name(now: datetime | None = None) -> str:
    """Rough trading-session label for small talk."""
    now = now or datetime.now(timezone.utc)
    h = now.hour
    if 0 <= h < 7:
        return "the Asian session"
    if 7 <= h < 12:
        return "the London session"
    if 12 <= h < 16:
        return "the London and New York overlap"
    if 16 <= h < 21:
        return "the New York session"
    return "the late New York hours"


def next_change(now: datetime | None = None) -> str:
    """Human phrase for when the primary chart switches next."""
    now = now or datetime.now(timezone.utc)
    if gold_market_open(now):
        if now.weekday() == 4:
            return "gold closes for the weekend at ten p.m. U T C tonight, then we move to Bitcoin"
        return "gold takes its daily break at ten p.m. U T C"
    if now.weekday() in (5, 6):
        return "gold reopens Sunday night at eleven p.m. U T C"
    return "gold reopens at eleven p.m. U T C"
