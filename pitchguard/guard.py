"""Orchestrates both lanes. Two entry points:

  Guard.audit_call(call)         - after the call: full report for a finished transcript
  Guard.check_utterance(...)     - during the call: allow / rewrite / block the bot's NEXT sentence
"""
from __future__ import annotations

import time
from typing import Optional

from pydantic import BaseModel

from . import claims, rules
from .models import SEV_RANK, SEV_WEIGHT, Call, CallReport, Fact, Product, TurnResult, Violation


class GuardDecision(BaseModel):
    decision: str                       # ALLOW | REWRITE | BLOCK
    violations: list[Violation]
    fast_lane_ms: float
    deep_lane_ms: Optional[float] = None
    suggested_fix: Optional[str] = None


def score_and_verdict(violations: list[Violation]) -> tuple[int, str]:
    best: dict[tuple, Violation] = {}                 # one penalty per (turn, category)
    for v in violations:
        k = (v.turn, v.category)
        if k not in best or SEV_RANK[v.severity] > SEV_RANK[best[k].severity]:
            best[k] = v
    score = max(0, 100 - sum(SEV_WEIGHT[v.severity] for v in best.values()))
    if any(SEV_RANK[v.severity] >= 3 for v in violations):
        return score, "BLOCK"
    return score, ("REVIEW" if violations else "PASS")


class Guard:
    def __init__(self, products: dict[str, Product], rulebook: dict, llm=None):
        self.products, self.rb, self.llm = products, rulebook, llm

    # ---------------------------------------------------------------- after the call
    def audit_call(self, call: Call, use_llm: bool = True, rewrite: bool = True) -> CallReport:
        t0 = time.perf_counter()
        llm = self.llm if use_llm else None
        facts: list[Fact] = list(self.products[call.product].facts) + list(call.account_facts)
        results: list[TurnResult] = []
        call_level = rules.check_call(call, self.rb)
        by_turn: dict[int, list[Violation]] = {}
        for v in list(call_level):
            if v.turn is not None:
                by_turn.setdefault(v.turn, []).append(v)
        call_level = [v for v in call_level if v.turn is None]

        for i, t in enumerate(call.turns):
            tr = TurnResult(turn=i, speaker=t.speaker, text=t.text)
            if t.speaker == "bot":
                tr.violations = rules.check_turn(t.text, call.scenario, self.rb, i) + by_turn.get(i, [])
                if llm and claims.needs_claim_check(t.text):
                    ctx = [f"{x.speaker.upper()}: {x.text}" for x in call.turns[max(0, i - 2): i]]
                    tr.violations += claims.check_claims(t.text, ctx, facts, llm, i)
                    tr.llm_checked = True
                if rewrite and llm and tr.violations:
                    tr.rewrite = claims.rewrite_turn(t.text, tr.violations, facts, llm)
            results.append(tr)

        all_v = [v for r in results for v in r.violations] + call_level
        score, verdict = score_and_verdict(all_v)
        return CallReport(
            call_id=call.id, title=call.title, scenario=call.scenario, mode="full" if llm else "rules",
            score=score, verdict=verdict, turns=results, call_violations=call_level,
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        )

    # ---------------------------------------------------------------- during the call
    def check_utterance(self, product_id: str, scenario: str, text: str, context: Optional[list[str]] = None,
                        deep: bool = False, account_facts: Optional[list[Fact]] = None) -> GuardDecision:
        t0 = time.perf_counter()
        viols = rules.check_turn(text, scenario, self.rb)
        fast_ms = (time.perf_counter() - t0) * 1000
        deep_ms = None
        facts = list(self.products[product_id].facts) + list(account_facts or [])
        if deep and self.llm and claims.needs_claim_check(text):
            t1 = time.perf_counter()
            viols += claims.check_claims(text, context or [], facts, self.llm)
            deep_ms = (time.perf_counter() - t1) * 1000
        worst = max((SEV_RANK[v.severity] for v in viols), default=0)
        decision = "BLOCK" if worst >= 3 else ("REWRITE" if viols else "ALLOW")
        fix = None
        if viols:
            fix = claims.rewrite_turn(text, viols, facts, self.llm) if (deep and self.llm) else viols[0].fix_hint
        return GuardDecision(decision=decision, violations=viols, fast_lane_ms=round(fast_ms, 3),
                             deep_lane_ms=round(deep_ms, 1) if deep_ms is not None else None, suggested_fix=fix)
