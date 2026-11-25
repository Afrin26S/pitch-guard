"""Fast lane: deterministic rules. Pure regex, no network, runs in well under a millisecond.

A bot that speaks in real time cannot wait seconds for a model to approve every sentence, so
everything that CAN be decided with code is decided with code, and only the genuinely semantic
questions ("is this benefit actually in the product sheet?") go to the slower LLM lane.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from .models import Call, Violation

FLAGS = re.IGNORECASE | re.UNICODE


@lru_cache(maxsize=4096)
def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, FLAGS)


def _negated(text: str, m: re.Match, neg_rx: re.Pattern) -> bool:
    """Is a negation word right before or after the match? ('guarantee nahi hai', 'not guaranteed')"""
    window = text[max(0, m.start() - 15): m.start()] + " " + text[m.end(): m.end() + 16]
    return bool(neg_rx.search(window))


def check_turn(text: str, scenario: str, rb: dict, turn: Optional[int] = None) -> list[Violation]:
    neg = _rx(rb["negation"])
    out: list[Violation] = []
    for rule in rb["turn_rules"]:
        only = rule.get("scenarios")
        if only and scenario not in only:
            continue
        hits: list[str] = []
        for pat in rule.get("patterns", []):
            m = _rx(pat).search(text)
            if m:
                hits.append(m.group(0))
        for pat in rule.get("soft_patterns", []):
            for m in _rx(pat).finditer(text):
                if not _negated(text, m, neg):
                    hits.append(m.group(0))
                    break
        if hits:
            out.append(Violation(
                turn=turn, rule_id=rule["id"], category=rule["category"], severity=rule["severity"],
                message=rule["message"], evidence=hits[0], source="rule", fix_hint=rule.get("fix_hint", ""),
            ))
    return out


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def check_call(call: Call, rb: dict) -> list[Violation]:
    """Rules that need the whole call: AI disclosure, call hours, identity-before-debt, disclosures."""
    out: list[Violation] = []
    bot = [(i, t.text) for i, t in enumerate(call.turns) if t.speaker == "bot"]

    # 1. The bot must say it is an AI early in the call.
    cfg = rb["ai_disclosure"]
    early = " ".join(t for _, t in bot[: cfg["within_bot_turns"]])
    if not any(_rx(p).search(early) for p in cfg["patterns"]):
        out.append(Violation(
            turn=None, rule_id="C-AI-DISCLOSURE", category="AI_DISCLOSURE", severity="high",
            message=f"No AI disclosure within the first {cfg['within_bot_turns']} bot turns.",
            fix_hint=cfg["fix_hint"],
        ))

    # 2. Call-hours window.
    window = rb["call_hours"].get(call.scenario)
    if call.time and window and not (_minutes(window[0]) <= _minutes(call.time) <= _minutes(window[1])):
        out.append(Violation(
            turn=None, rule_id="C-CALL-HOURS", category="CALL_HOURS", severity="high",
            message=f"Call placed at {call.time}, outside the allowed {window[0]}-{window[1]} window for {call.scenario}.",
            fix_hint="Schedule the call inside the permitted window.",
        ))

    # 3. Collections: do not mention the debt before the borrower confirms who they are.
    idc = rb["identity_before_debt"]
    if call.scenario in idc["scenarios"]:
        confirmed = False
        for i, turn in enumerate(call.turns):
            if turn.speaker == "customer":
                if any(_rx(p).search(turn.text) for p in idc["confirm_patterns"]):
                    confirmed = True
                continue
            if not confirmed and any(_rx(p).search(turn.text) for p in idc["debt_patterns"]):
                m = next(_rx(p).search(turn.text) for p in idc["debt_patterns"] if _rx(p).search(turn.text))
                out.append(Violation(
                    turn=i, rule_id="C-IDENTITY-BEFORE-DEBT", category="PRIVACY", severity="high",
                    message="Debt details mentioned before the borrower confirmed their identity.",
                    evidence=m.group(0), fix_hint=idc["fix_hint"],
                ))

    # 4. Required disclosures: if the bot talks about X, it must also say Y somewhere in the call.
    bot_text = " ".join(t for _, t in bot)
    for d in rb.get("required_disclosures", {}).get(call.scenario, []):
        if _rx(d["trigger"]).search(bot_text) and not _rx(d["satisfied_by"]).search(bot_text):
            out.append(Violation(
                turn=None, rule_id=d["id"], category="MISSING_DISCLOSURE", severity="medium",
                message=d["text"], fix_hint=d["text"],
            ))
    return out
