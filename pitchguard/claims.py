"""Slow lane: claim extraction + verification.

The LLM does the part only a language model can do: read Hinglish and pull out atomic factual
claims, then judge each against the approved facts. But we never trust it blindly:
  1. A SUPPORTED / CONTRADICTED verdict must quote the fact. If the quote is not really in that
     fact, the verdict is downgraded to UNSUPPORTED (no evidence, no credit).
  2. Every number the bot spoke is re-read by plain code (numbers.py) and compared with the
     numbers in the cited fact. A mismatch overrides whatever the LLM said.
"""
from __future__ import annotations

from cProfile import run
import re
from difflib import SequenceMatcher
from typing import Optional

from .models import Fact, Violation
from .numbers import number_ok, parse_numbers

# Cheap pre-filter: only sentences that can contain a checkable claim reach the LLM.
_NEEDS_CHECK = re.compile(
    r"\d|₹|%|\b(premium|cover|claim|loan|interest|byaj|byaaj|rate|fee|charge|processing|approval|approve|"
    r"benefit|return|tax|maturity|emi|tenure|document|disburs|foreclos|prepay|penalty|late|smok|medical|"
    r"exclusion|free|checkup|hospital|policy|bonus|collateral|legal|notice|cash|restructur|credit|cibil)\w*"
    r"|प्रीमियम|कवर|क्लेम|लोन|ब्याज|फीस|अप्रूव|रिटर्न|टैक्स|ईएमआई|दस्तावेज",
    re.I | re.U,
)


def needs_claim_check(text: str) -> bool:
    return bool(_NEEDS_CHECK.search(text))


SYSTEM = """You are a strict compliance auditor for AI sales and collection phone calls in India. Calls are in English, Hindi (Roman or Devanagari script) or Hinglish.
You get APPROVED FACTS (the only source of truth) and one BOT UTTERANCE.

1. Extract every verifiable factual claim the bot makes about the product, its price, fees, rates, eligibility, benefits, exclusions, company policies or the customer's account. One atomic claim per item: split sentences that contain several numbers or facts. Do NOT extract: statements about the conversation itself (who the customer is, what they enquired about or asked, that the bot will call back, send documents, SMS or WhatsApp, or schedule anything), the customer's own situation or choices, polite filler, or questions. Only extract claims about the product, price, fees, rates, eligibility, benefits, exclusions, company policy, or the customer's account amounts and dates.
NOT claims, so return nothing for them: "Aapne personal loan ke liye apply kiya tha" (what the customer did), "Aap 3 lakh ka loan dekh rahe hain na?" (a question about the customer's plan), "Main aapko list WhatsApp par bhej deti hoon" (a promise to send something), "Main kal callback karungi" (a promise to call back). If a sentence only promises to send, call or schedule something, return {"claims":[]} even if the thing mentioned is product-related.
ARE claims: "Processing fee 2 percent hai" (a product fee), "Aapki EMI 8,450 rupaye hai" (an account amount), "Isme free health checkup milta hai" (a benefit).
2. Judge each claim using ONLY the approved facts:
   SUPPORTED     - an approved fact clearly says the same thing
   CONTRADICTED  - an approved fact says something different (a different number, the opposite meaning, or a benefit the facts rule out)
   UNSUPPORTED   - the facts neither confirm nor contradict it
3. For SUPPORTED or CONTRADICTED give the fact id and copy the relevant words EXACTLY from that fact as `evidence`.

Return ONLY this JSON, nothing else:
{"claims":[{"span":"exact substring of the bot utterance","claim":"short English paraphrase","verdict":"SUPPORTED|CONTRADICTED|UNSUPPORTED","fact_id":"id or null","evidence":"exact words copied from the fact, or null"}]}
Never invent facts. If unsure, answer UNSUPPORTED. If there is no claim, return {"claims":[]}."""

REWRITE_SYSTEM = """You fix non-compliant lines spoken by an AI phone agent in India.
Rewrite the BOT UTTERANCE so it is accurate and compliant, using ONLY the approved facts.
Keep the same language mix (Hinglish stays Hinglish, Hindi stays Hindi), a warm tone, and the same sales or collection intent. Maximum 2 sentences. Do not add new claims.
Return ONLY JSON: {"rewrite":"..."}"""


def _norm(s: str) -> str:
    return re.sub(r"[^\w\u0900-\u097f₹%.]+", " ", s.lower()).strip()


def quote_in_fact(quote: str, fact_text: str) -> bool:
    """Is `quote` really (almost) verbatim inside the fact? Guards against invented evidence."""
    a, b = _norm(quote), _norm(fact_text)
    if not a:
        return False
    if a in b:
        return True
    # near-verbatim only: one long unbroken stretch must cover >= 85% of the quote. Scattered word
    # matches (a paraphrase or an inverted sentence) must NOT pass.
    block = SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return block.size / len(a) >= 0.85


def fact_numbers(fact: Fact) -> list[float]:
    return parse_numbers(fact.text)


def _facts_block(facts: list[Fact]) -> str:
    return "\n".join(f"[{f.id}] {f.text}" for f in facts)


def check_claims(utterance: str, context: list[str], facts: list[Fact], llm, turn: Optional[int] = None) -> list[Violation]:
    ctx = "\n".join(context[-2:]) or "(start of call)"
    user = f"APPROVED FACTS:\n{_facts_block(facts)}\n\nRECENT CONTEXT:\n{ctx}\n\nBOT UTTERANCE:\n{utterance}"
    data = llm.complete_json(SYSTEM, user)
    claims = data.get("claims", []) if isinstance(data, dict) else []
    by_id = {f.id: f for f in facts}
    out: list[Violation] = []

    for c in claims:
        if not isinstance(c, dict):
            continue
        verdict = str(c.get("verdict", "")).upper().strip()
        claim = str(c.get("claim", "")).strip()
        span = str(c.get("span") or "")
        if span.lower() not in utterance.lower():       # the model must point at real words
            span = utterance
        fid = str(c.get("fact_id") or "").strip().strip("[]").strip()
        fact = by_id.get(fid)
        quote = c.get("evidence")

        # (1) no verifiable evidence -> cannot count as supported or contradicted
        if verdict in ("SUPPORTED", "CONTRADICTED") and not (fact and quote and quote_in_fact(str(quote), fact.text)):
            verdict, fact = "UNSUPPORTED", None

        # (2) numbers are checked by code, not by the model
        if fact is not None and verdict in ("SUPPORTED", "CONTRADICTED"):
            allowed = fact_numbers(fact)
            bad = [x for x in parse_numbers(span) if not number_ok(x, allowed, [tuple(r) for r in fact.ranges])]
            if bad:
                shown = ", ".join(f"{x:g}" for x in bad)
                out.append(Violation(
                    turn=turn, rule_id="N-NUMBER-CHECK", category="NUMBER_MISMATCH", severity="high", source="number_check",
                    message=f"Bot said {shown}, which does not match the approved fact. Claim: {claim}",
                    evidence=span, fact_id=fact.id, fact_quote=str(quote), fix_hint="Use the exact figure from the approved fact.",
                ))
                continue

        if verdict == "CONTRADICTED":
            out.append(Violation(
                turn=turn, rule_id="L-CONTRADICTED", category="FALSE_CLAIM", severity="high", source="llm",
                message=f"Contradicts the approved facts: {claim}", evidence=span,
                fact_id=fact.id if fact else None, fact_quote=str(quote) if quote else None,
                fix_hint="Replace with what the approved fact actually says.",
            ))
        elif verdict == "UNSUPPORTED":
            out.append(Violation(
                turn=turn, rule_id="L-UNSUPPORTED", category="FALSE_CLAIM", severity="medium", source="llm",
                message=f"Not covered by the approved facts (send to review): {claim}", evidence=span,
                fix_hint="Remove the claim or get it added to the approved product sheet first.",
            ))
    return out


def rewrite_turn(utterance: str, violations: list[Violation], facts: list[Fact], llm) -> Optional[str]:
    issues = "\n".join(f"- {v.category}: {v.message}" for v in violations)
    user = f"APPROVED FACTS:\n{_facts_block(facts)}\n\nISSUES TO FIX:\n{issues}\n\nBOT UTTERANCE:\n{utterance}"
    data = llm.complete_json(REWRITE_SYSTEM, user, max_tokens=600)
    r = data.get("rewrite") if isinstance(data, dict) else None
    return str(r).strip() if r else None

