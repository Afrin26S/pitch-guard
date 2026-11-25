"""Read amounts the way Indian callers say them: 50 lakh, ₹8,450, pachaas hazaar, 2 crore, 97.8%.

Why code instead of the LLM? Language models are unreliable at exact numbers (they happily treat
349 and 549 as "close enough"). Every number a bot speaks is therefore parsed and compared by
plain code against the approved fact it claims to rely on.
"""
from __future__ import annotations

import re

_DEV = str.maketrans("०१२३४५६७८९", "0123456789")

WORDS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "terah": 13, "pandrah": 15,
    "bees": 20, "pachees": 25, "tees": 30, "chalis": 40, "chalees": 40, "pachaas": 50, "pachas": 50,
    "saath": 60, "sattar": 70, "assi": 80, "nabbe": 90,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "zero": 0, "shunya": 0,
}
ALWAYS_NUMBER = {"zero", "shunya"}            # accepted even without a unit
MULT = {
    "sau": 100, "hundred": 100, "hazaar": 1000, "hazar": 1000, "thousand": 1000, "k": 1000,
    "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000,
    "crore": 10_000_000, "crores": 10_000_000, "cr": 10_000_000, "million": 1_000_000,
    # Devanagari
    "सौ": 100, "हजार": 1000, "हज़ार": 1000, "लाख": 100_000, "करोड़": 10_000_000, "करोड": 10_000_000,
}
UNITS = {
    "rupaye", "rupees", "rupee", "rs", "inr", "percent", "pratishat", "saal", "sal", "varsh", "years",
    "year", "mahine", "mahina", "months", "month", "din", "days", "day", "ghante", "hours", "hour",
    "minute", "minutes",
    "रुपये", "रुपए", "रूपये", "प्रतिशत", "साल", "महीने", "महीना", "दिन", "घंटे",
}
CURRENCY = {"₹", "rs", "inr", "rupaye", "rupees", "rupee", "रुपये", "रुपए"}

# digits (with Indian commas), words in Latin or Devanagari script, and the rupee / percent signs
_TOK = re.compile(r"\d[\d,]*(?:\.\d+)?|[a-z\u0900-\u097f]+|₹|%")


def _val(tok: str):
    if tok[0].isdigit():
        try:
            return float(tok.replace(",", ""))
        except ValueError:
            return None
    return WORDS.get(tok)


def parse_numbers(text: str) -> list[float]:
    """Return every amount found in `text` as a float, in order of appearance.

    Digits always count. A number WORD ("do", "paanch") only counts when it is followed by a
    multiplier or unit ("do lakh", "paanch saal"), because "do" also means "give" in Hindi
    ("details bhej do").
    """
    toks = _TOK.findall(text.translate(_DEV).lower())
    n, i, out = len(toks), 0, []
    while i < n:
        tok = toks[i]
        v = _val(tok)
        if v is None:
            i += 1
            continue
        if not tok[0].isdigit() and tok not in ALWAYS_NUMBER:
            nxt = toks[i + 1] if i + 1 < n else ""
            prev = toks[i - 1] if i else ""
            if not (nxt in MULT or nxt in UNITS or prev in CURRENCY):
                i += 1
                continue
        total, cur, j, last = 0.0, v, i + 1, None
        while j < n and toks[j] in MULT:
            m = MULT[toks[j]]
            if last is not None and m >= last:
                break
            total += (cur if cur is not None else 1) * m
            cur, last, j = None, m, j + 1
            # "2 lakh 50 hazaar": a plain number followed by a SMALLER multiplier continues the amount
            if j + 1 < n and _val(toks[j]) is not None and toks[j + 1] in MULT and MULT[toks[j + 1]] < m:
                cur, j = _val(toks[j]), j + 1
            else:
                break
        if cur is not None:
            total += cur
        out.append(total)
        i = max(j, i + 1)
    return out


def number_ok(x: float, allowed: list[float], ranges: list[tuple[float, float]], tol: float = 0.01) -> bool:
    """Is `x` one of the approved numbers (within 1%) or inside an approved range?"""
    if any(abs(x - a) <= tol * max(abs(a), 1.0) for a in allowed):
        return True
    return any(lo <= x <= hi for lo, hi in ranges)
