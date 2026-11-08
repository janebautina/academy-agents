"""Read donations from DonationAlerts and decide which ones are course purchases.

A donation is about the course when its message has an email address (the payment page asks
buyers to write their email) or the word КУРС / COURSE. It is delivered automatically when it
has an email and an amount at or above the course price in its currency (COURSE_PRICES in .env,
default "RUB:2990,USD:49,EUR:45"). A donation with neither is an ordinary stream donation and
is left alone.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from core import env

API = "https://www.donationalerts.com/api/v1/alerts/donations"
KEYWORD = re.compile(r"(?<![\w])(курс|course)(?![\w])", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


@dataclass
class Purchase:
    donation_id: int
    name: str
    email: str            # "" when the buyer forgot it
    amount: float
    currency: str
    lang: str             # "ru" or "en"
    paid_enough: bool
    created_at: str


def prices() -> dict[str, float]:
    raw = env.get("COURSE_PRICES", "RUB:2990,USD:49,EUR:45")
    return {c.strip().upper(): float(v) for c, v in (p.split(":") for p in raw.split(",") if ":" in p)}


def parse(d: dict) -> Purchase | None:
    """One DonationAlerts donation → a Purchase, or None if it is not about the course."""
    message = d.get("message") or ""
    email = EMAIL.search(message)
    if not email and not KEYWORD.search(message):
        return None
    currency = (d.get("currency") or "").upper()
    amount = float(d.get("amount") or 0)
    price = prices().get(currency)
    lang = "ru" if currency == "RUB" or re.search(r"курс", message, re.I) else "en"
    return Purchase(
        donation_id=int(d["id"]), name=d.get("username") or "", email=email.group(0).lower().rstrip(".") if email else "",
        amount=amount, currency=currency, lang=lang, paid_enough=price is not None and amount >= price,
        created_at=d.get("created_at") or "")


def created(d: dict) -> datetime:
    """DonationAlerts writes dates as 'YYYY-MM-DD HH.MM.SS' (UTC)."""
    return datetime.strptime(d["created_at"].replace(".", ":"), "%Y-%m-%d %H:%M:%S")


def fetch(pages: int = 3) -> list[dict]:
    """Newest donations first; a few pages are plenty for a run every 15–30 minutes."""
    out = []
    for page in range(1, pages + 1):
        request = urllib.request.Request(f"{API}?{urllib.parse.urlencode({'page': page})}",
                                         headers={"Authorization": f"Bearer {env.need('DA_ACCESS_TOKEN')}"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                answer = json.load(response)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"DonationAlerts {e.code}: токен устарел или неверный / token expired or wrong") from None
        out += answer.get("data", [])
        if page >= answer.get("meta", {}).get("last_page", 1):
            break
    return out
