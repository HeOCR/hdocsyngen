"""Generated values: amounts, dates, percentages, quantities, item numbers, IDs, e-mail addresses and URLs.

Everything is drawn from a seeded `random.Random`. ID-like numbers are made to FAIL the Israeli check digit, so a
generated ID can never be a real person's or company's. E-mail addresses and URLs use the reserved example.com domain.
No phone numbers and no personal names are generated (a generated number or name could be a real one).
"""
from __future__ import annotations

import random

from .tree import Run

HEBREW_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר",
                 "דצמבר"]


def _group(n: int) -> str:
    return f"{n:,}"


def amount(rng: random.Random, lo: int = 100, hi: int = 2_000_000) -> list[Run]:
    """An amount with the shekel sign before or after, or 'ש"ח' after; sometimes with agorot."""
    v = rng.randint(lo, hi)
    s = _group(v) + (f".{rng.randint(0, 99):02d}" if rng.random() < 0.3 else "")
    style = rng.random()
    if style < 0.4:
        return [Run("₪ " + s, "num", kind="amount")]
    if style < 0.7:
        return [Run(s + " ₪", "num", kind="amount")]
    return [Run(s, "num", kind="amount"), Run(' ש"ח', "he")]


def bare_amount(rng: random.Random, lo: int = 1, hi: int = 500_000) -> tuple[int, str]:
    v = rng.randint(lo, hi)
    return v, _group(v)


def date(rng: random.Random, year_lo: int = 2024, year_hi: int = 2027) -> list[Run]:
    y, m, d = rng.randint(year_lo, year_hi), rng.randint(1, 12), rng.randint(1, 28)
    style = rng.random()
    if style < 0.45:
        return [Run(f"{d}.{m}.{y}", "num", kind="date")]
    if style < 0.75:
        return [Run(f"{d:02d}/{m:02d}/{y % 100:02d}", "num", kind="date")]
    return [Run(f"{d} ב{HEBREW_MONTHS[m - 1]} {y}", "he", kind="date")]


def percent(rng: random.Random) -> list[Run]:
    v = rng.choice([rng.randint(1, 100), round(rng.uniform(0.5, 30), 1)])
    return [Run(f"{v}%", "num", kind="percent")]


def item_no(rng: random.Random, depth: int | None = None) -> str:
    depth = depth or rng.randint(2, 3)
    return ".".join(str(rng.randint(1, 12)) for _ in range(depth))


def _check_digit(digits8: str) -> int:
    total = 0
    for i, ch in enumerate(digits8):
        x = int(ch) * (1 if i % 2 == 0 else 2)
        total += x - 9 if x > 9 else x
    return (10 - total % 10) % 10


def is_valid_il_id(s: str) -> bool:
    d = s.replace("-", "")
    if len(d) != 9 or not d.isdigit():
        return False
    return _check_digit(d[:8]) == int(d[8])


def fake_id(rng: random.Random, company: bool = False) -> list[Run]:
    """A 9-digit ID-like number whose check digit is deliberately wrong."""
    body = ("51" if company else str(rng.randint(1, 3))) + "".join(str(rng.randint(0, 9)) for _ in range(8))
    body = body[:8]
    bad = (_check_digit(body) + rng.randint(1, 9)) % 10
    s = body + str(bad)
    assert not is_valid_il_id(s)
    text = f"{s[:2]}-{s[2:8]}-{s[8]}" if company else s
    return [Run(text, "num", kind="id")]


def email(rng: random.Random) -> list[Run]:
    user = rng.choice(["info", "office", "tenders", "procurement", "contact", "support"])
    return [Run(f"{user}{rng.randint(1, 99)}@example.com", "en", kind="email")]


def url(rng: random.Random) -> list[Run]:
    path = rng.choice(["tenders", "docs", "forms", "notices"])
    return [Run(f"https://www.example.com/{path}/{rng.randint(100, 9999)}", "en", kind="url")]


def tender_ref(rng: random.Random) -> list[Run]:
    return [Run(f"{rng.randint(1, 99)}/{rng.randint(2024, 2027)}", "num", kind="ref")]
