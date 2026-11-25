"""Pitch Guard dashboard.   streamlit run app.py"""
import json
import re

import pandas as pd
import streamlit as st

from pitchguard.guard import Guard
from pitchguard.kb import ROOT, load_calls, load_products, load_rulebook, parse_turns
from pitchguard.llm import get_llm
from pitchguard.models import Call, CallReport

st.set_page_config(page_title="Pitch Guard", page_icon="🛡️", layout="wide")
RESULTS = ROOT / "results"
SCENARIOS = {"term_sales": "term_shield", "loan_sales": "quickcash_loan", "collections": "quickcash_loan"}
ICON = {"critical": "🛑", "high": "🔴", "medium": "🟠", "low": "🟡"}


@st.cache_resource
def load_all():
    return load_products(), load_rulebook(), load_calls(), get_llm()


products, rulebook, calls, llm = load_all()
guard = Guard(products, rulebook, llm)


def hl(text: str, evidences) -> str:
    """Highlight the exact words a rule or the verifier pointed at."""
    out = text.replace("$", r"\$")
    for ev in sorted({e for e in evidences if e}, key=len, reverse=True):
        out = re.sub(re.escape(ev.replace("$", r"\$")), lambda m: f":red-background[{m.group(0)}]", out, count=1, flags=re.I)
    return out


def get_report(call: Call) -> CallReport:
    key = f"report::{call.id}::{'full' if llm else 'rules'}"
    if key not in st.session_state:
        cached = RESULTS / "full" / f"{call.id}.json"
        if llm:
            with st.spinner("Checking every bot sentence (rules + Groq claim verifier)..."):
                st.session_state[key] = guard.audit_call(call, use_llm=True, rewrite=True)
        elif cached.exists():
            st.session_state[key] = CallReport.model_validate_json(cached.read_text(encoding="utf-8"))
        else:
            st.session_state[key] = guard.audit_call(call, use_llm=False, rewrite=False)
    return st.session_state[key]


def show_report(report: CallReport):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Verdict", report.verdict)
    c2.metric("Compliance score", f"{report.score}/100")
    c3.metric("Violations", len(report.all_violations()))
    c4.metric("Checked with", "Rules + LLM verifier" if report.mode == "full" else "Rules only")
    if report.mode == "rules":
        st.caption("Rules-only view: wrong numbers and invented benefits need the LLM verifier, which is switched off here "
                   "(no API key in this deployment and no cached full run for this call).")
    for v in report.call_violations:
        st.warning(f"{ICON[v.severity]} **{v.category}** (whole call) - {v.message}")
    st.divider()
    for tr in report.turns:
        with st.chat_message("assistant" if tr.speaker == "bot" else "user"):
            st.markdown(hl(tr.text, [v.evidence for v in tr.violations]))
            for v in tr.violations:
                body = f"{ICON[v.severity]} **{v.category}** · {v.severity} · via {v.source} — {v.message}"
                (st.error if v.severity in ("high", "critical") else st.warning)(body)
                if v.fact_quote:
                    st.caption(f"Approved fact `{v.fact_id}`: “{v.fact_quote}”")
            if tr.rewrite:
                st.success(f"Compliant rewrite: {tr.rewrite}")
            elif tr.violations and tr.violations[0].fix_hint:
                st.info(f"Fix: {tr.violations[0].fix_hint}")


st.title("🛡️ Pitch Guard")
st.caption("A compliance and fact-check guardrail for persuasive sales and collection voice bots. "
           "Built on public information, with synthetic calls and fictional products.")

tab_audit, tab_live, tab_eval, tab_about = st.tabs(["Audit a call", "Live guard", "Evaluation", "How it works"])

# ---------------------------------------------------------------------------------------------
with tab_audit:
    st.write("Pick a synthetic call. Every bot sentence is checked against the approved product sheet and the rulebook.")
    pick = st.selectbox("Call", calls, format_func=lambda c: f"{c.title}  ·  {c.scenario}")
    show_report(get_report(pick))
    with st.expander("Audit your own transcript"):
        sc = st.selectbox("Scenario", list(SCENARIOS), key="own_sc")
        t = st.text_input("Call time (HH:MM, 24h)", "11:00")
        raw = st.text_area("Transcript, one turn per line: B: = bot, C: = customer", height=180, value=(
            "B: Namaste, main Aarohi bol rahi hoon, ek AI assistant.\nC: Haan boliye\n"
            "B: Sir ye plan 12 percent guaranteed return deta hai, koi risk nahi."))
        if st.button("Audit this transcript"):
            own = Call(id="own", title="Your transcript", scenario=sc, product=SCENARIOS[sc], time=t,
                       turns=parse_turns([l for l in raw.splitlines() if l.strip()]))
            show_report(guard.audit_call(own, use_llm=bool(llm), rewrite=bool(llm)))

# ---------------------------------------------------------------------------------------------
with tab_live:
    st.write("This is what a voice bot would call **before speaking each sentence**. "
             "The fast lane is plain regex and answers in well under a millisecond; the deep lane adds the LLM claim check.")
    examples = {
        "Guaranteed returns (term)": ("term_sales", "Sir, isme har saal 12 percent guaranteed return milta hai aur koi risk nahi hai."),
        "Fake deadline (term)": ("term_sales", "Ye offer sirf aaj ke liye hai, kal se premium badh jayega."),
        "Safe: guarantee is negated": ("term_sales", "Claim ratio 97.8 percent tha, lekin ye future ke liye guarantee nahi hai."),
        "Approval promise (loan)": ("loan_sales", "Aapka loan pakka approve ho jayega, koi CIBIL check nahi hoga."),
        "Threat (collections)": ("collections", "Payment nahi hua toh hum police ko bhejenge aur ghar walon ko bata denge."),
        "Claims to be human": ("term_sales", "Nahi sir, main ek real insaan hoon, robot nahi hoon."),
    }
    ex = st.selectbox("Try an example (or type your own below)", list(examples))
    sc_default, text_default = examples[ex]
    sc = st.selectbox("Scenario", list(SCENARIOS), index=list(SCENARIOS).index(sc_default), key=f"sc_{ex}")
    text = st.text_area("Next bot sentence", text_default, key=f"txt_{ex}")
    deep = st.checkbox("Deep check with the LLM claim verifier", value=False, disabled=llm is None,
                       help="Needs GROQ_API_KEY. Without a key only the fast lane runs.")
    d = guard.check_utterance(SCENARIOS[sc], sc, text, deep=deep)
    banner = {"BLOCK": st.error, "REWRITE": st.warning, "ALLOW": st.success}[d.decision]
    banner(f"Decision: **{d.decision}**")
    m1, m2 = st.columns(2)
    m1.metric("Fast lane (regex rules)", f"{d.fast_lane_ms:.2f} ms")
    m2.metric("Deep lane (LLM)", f"{d.deep_lane_ms:.0f} ms" if d.deep_lane_ms is not None else "not run")
    for v in d.violations:
        st.markdown(f"{ICON[v.severity]} **{v.category}** · {v.severity} — {v.message}  \n`{v.evidence}`")
    if d.suggested_fix:
        st.info(f"Suggested fix: {d.suggested_fix}")

# ---------------------------------------------------------------------------------------------
with tab_eval:
    st.write("Development set: 16 synthetic calls with violations planted at known positions.")
    res = {m: json.loads((RESULTS / f"eval_{m}.json").read_text(encoding="utf-8"))
           for m in ("rules", "full") if (RESULTS / f"eval_{m}.json").exists()}
    if not res:
        st.info("No results yet. Run `python -m pitchguard.evaluate --mode rules`.")
    else:
        rows = [{"Lane": "Rules only" if m == "rules" else "Rules + LLM verifier",
                 "Planted violations found": f"{r['detected']}/{r['planted_violations']}",
                 "Recall": f"{r['label_recall']:.0%}",
                 "Clean turns wrongly flagged": f"{r['clean_turns_flagged']}/{r['clean_bot_turns']}",
                 "Model": r.get("model") or "-"} for m, r in res.items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        cats = list(next(iter(res.values()))["per_category"])
        table = {"Category": cats}
        for m, r in res.items():
            table["Rules only" if m == "rules" else "Rules + LLM"] = [
                f"{r['per_category'][c]['detected']}/{r['per_category'][c]['planted']}" for c in cats]
        st.dataframe(pd.DataFrame(table), hide_index=True)
        for m, r in res.items():
            with st.expander(f"{m}: misses, false positives and extra flags"):
                st.write("**Missed**", r["missed"] or "none")
                st.write("**False positives (clean turn flagged)**", r["false_positives"] or "none")
                st.write("**Extra categories on labelled turns (review by hand)**", r["extra_flags_to_review"] or "none")
    held = {m: json.loads((RESULTS / f"eval_{m}_heldout.json").read_text(encoding="utf-8"))
            for m in ("rules", "full") if (RESULTS / f"eval_{m}_heldout.json").exists()}
    if held:
        st.subheader("Held-out calls (written after the rules and prompt were frozen)")
        st.dataframe(pd.DataFrame([{
            "Lane": "Rules only" if m == "rules" else "Rules + LLM verifier",
            "Calls": r["calls"],
            "Planted violations found": f"{r['detected']}/{r['planted_violations']}",
            "Clean turns wrongly flagged": f"{r['clean_turns_flagged']}/{r['clean_bot_turns']}",
        } for m, r in held.items()]), hide_index=True)
    st.warning("Read with care: the development numbers are optimistic, because the calls, rules and prompt were written and tuned together. "
               "The held-out set is only 6 calls with 4 planted violations (wrong numbers and invented claims), so a perfect score there is encouraging, not proof.")

# ---------------------------------------------------------------------------------------------
with tab_about:
    st.markdown("""
**The problem.** Persuasive voice bots are paid to close. That is exactly when a bot is tempted to promise
“guaranteed returns”, invent a deadline, misquote a fee or lean on a borrower. In insurance, lending and collections
each of those is a liability for the bank, not just for the bot vendor.

**Two lanes, because latency matters on a phone call.**
1. *Fast lane* (regex, under a millisecond): guarantee and risk-free language (Roman and Devanagari Hindi, English),
   false urgency, pressure, threats, claims to be human, AI disclosure, call hours, identity-before-debt, required disclosures.
   Negation-aware, so “guarantee nahi hai” is allowed.
2. *Deep lane* (LLM, runs only on sentences that contain a checkable claim): extracts atomic claims and judges each against
   the approved product sheet. It must **quote the fact**; a made-up quote is rejected. **Every number is re-checked by code**,
   because language models are bad at exact figures (₹349 vs ₹549).

**Limits, stated plainly.** Synthetic calls. Fictional products. Illustrative rules, not legal advice. Small test set written
by the same author as the rules. Built from public information about the voice-AI market, not from any company's internal data.
""")