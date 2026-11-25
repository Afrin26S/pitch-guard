"""Measure the guard against the labelled synthetic calls.

    python -m pitchguard.evaluate --mode rules     # offline, no key needed
    python -m pitchguard.evaluate --mode full      # rules + Groq claim verifier (needs GROQ_API_KEY)

Numbers reported:
  label recall          - of the planted violations, how many did we flag with the RIGHT category?
  clean-turn FP rate    - of bot turns with NO planted violation, how many did we flag anyway?
  per-category recall   - where each lane is strong or blind
Predictions that land on an already-labelled turn but with an extra category are listed for manual
review instead of being counted as errors (they may well be correct).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from .guard import Guard
from .kb import ROOT, load_calls, load_products, load_rulebook
from .llm import get_llm
from .models import CATEGORIES

RESULTS = ROOT / "results"


def evaluate(mode: str, calls_file=None, tag: str = "") -> dict:
    llm = get_llm() if mode == "full" else None
    if mode == "full" and llm is None:
        raise SystemExit("Set GROQ_API_KEY first (see README).")
    guard = Guard(load_products(), load_rulebook(), llm)
    out_dir = RESULTS / (mode + tag)
    out_dir.mkdir(parents=True, exist_ok=True)

    tp = defaultdict(int)
    total = defaultdict(int)
    missed, extras, fps = [], [], []
    clean_turns = flagged_clean = 0
    n_calls = 0

    for call in load_calls(Path(calls_file) if calls_file else None):
        report = guard.audit_call(call, use_llm=(mode == "full"), rewrite=(mode == "full"))
        (out_dir / f"{call.id}.json").write_text(report.model_dump_json(indent=1), encoding="utf-8")
        n_calls += 1
        pred = {(v.turn, v.category) for v in report.all_violations()}
        gold = {(l.turn, l.category) for l in call.labels}
        gold_turns = {t for t, _ in gold if t is not None}
        for g in gold:
            total[g[1]] += 1
            if g in pred:
                tp[g[1]] += 1
            else:
                missed.append({"call": call.id, "turn": g[0], "category": g[1]})
        for i, t in enumerate(call.turns):
            if t.speaker != "bot":
                continue
            turn_pred = {c for (tt, c) in pred if tt == i}
            if i not in gold_turns:
                clean_turns += 1
                if turn_pred:
                    flagged_clean += 1
                    fps.append({"call": call.id, "turn": i, "flagged": sorted(turn_pred), "text": t.text})
            else:
                for c in sorted(turn_pred - {c for (tt, c) in gold if tt == i}):
                    extras.append({"call": call.id, "turn": i, "extra_category": c, "text": t.text})
        for (tt, c) in pred:                                   # call-level predictions that are not labelled
            if tt is None and (None, c) not in gold:
                extras.append({"call": call.id, "turn": None, "extra_category": c, "text": ""})

    n_gold, n_tp = sum(total.values()), sum(tp.values())
    result = {
        "mode": mode,
        "model": getattr(llm, "model", None),
        "calls": n_calls,
        "planted_violations": n_gold,
        "detected": n_tp,
        "label_recall": round(n_tp / n_gold, 3) if n_gold else None,
        "clean_bot_turns": clean_turns,
        "clean_turns_flagged": flagged_clean,
        "clean_turn_fp_rate": round(flagged_clean / clean_turns, 3) if clean_turns else None,
        "per_category": {c: {"detected": tp[c], "planted": total[c]} for c in CATEGORIES if total[c]},
        "missed": missed,
        "false_positives": fps,
        "extra_flags_to_review": extras,
    }
    (RESULTS / f"eval_{mode}{tag}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    return result


def print_summary(r: dict) -> None:
    print(f"\nMODE: {r['mode']}   calls: {r['calls']}   model: {r['model']}")
    print(f"label recall      : {r['detected']}/{r['planted_violations']} = {r['label_recall']:.0%}")
    print(f"clean-turn FP rate: {r['clean_turns_flagged']}/{r['clean_bot_turns']} = {r['clean_turn_fp_rate']:.1%}")
    print("per category:")
    for c, d in r["per_category"].items():
        print(f"  {c:20} {d['detected']}/{d['planted']}")
    if r["missed"]:
        print("missed:", ", ".join(f"{m['call']}#{m['turn']}:{m['category']}" for m in r["missed"]))
    if r["false_positives"]:
        print("false positives:")
        for f in r["false_positives"]:
            print(f"  {f['call']}#{f['turn']} {f['flagged']}  {f['text'][:70]}")
    if r["extra_flags_to_review"]:
        print("extra flags on labelled turns (review by hand):")
        for e in r["extra_flags_to_review"]:
            print(f"  {e['call']}#{e['turn']} +{e['extra_category']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["rules", "full"], default="rules")
    ap.add_argument("--calls")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    print_summary(evaluate(a.mode, a.calls, a.tag))
