# 🛡️ Pitch Guard

**Live demo:** https://your-app-name.streamlit.app
**Demo Video:** https://youtu.be/TqlGDZFUjOY

**A compliance and fact-check guardrail for persuasive sales and collection voice bots.**
It checks every sentence a bot is about to say (or has said) against an approved product sheet and a rulebook, in English, Hindi (Roman and Devanagari script) and Hinglish.

> Built from public information about the voice-AI market, using synthetic calls and fictional products.
> No company's internal data was used. The rules are illustrative, not legal advice.

## Why this exists

Voice bots that sell insurance and loans, or collect overdue EMIs, are paid to persuade. That is exactly where
mis-selling ("12% guaranteed returns"), invented deadlines, wrong fees and threatening collection language creep in,
and each one is a liability for the bank that deployed the bot. Pitch Guard is a small, testable layer that catches
those problems before they are spoken, or audits them after the call.

## What it catches

| Category | Example | Lane |
|---|---|---|
| GUARANTEE | "guaranteed return", "koi risk nahi", "loan pakka approve", "पक्का अप्रूव" (negation-aware: "guarantee nahi hai" is allowed) | rules |
| URGENCY / PRESSURE | "sirf aaj ke liye", "kal se rate badh jayega", "abhi decide kijiye" | rules |
| THREAT | police, "ghar walon ko bata denge", shaming (collections) | rules |
| AI_DISCLOSURE | no early "I am an AI", or "main real insaan hoon" | rules |
| CALL_HOURS | call placed outside the allowed window | rules |
| PRIVACY | debt discussed before the borrower confirmed who they are | rules |
| MISSING_DISCLOSURE | premium or rate quoted without "depends on age / credit profile" | rules |
| NUMBER_MISMATCH | ₹349 instead of ₹549, "10 se 60 saal" instead of 18 to 60 | **code** (`numbers.py`), after LLM claim extraction |
| FALSE_CLAIM | invented "free health checkup", "claims kabhi reject nahi hote", "cash agent ko de dijiye" | **LLM**, with a mandatory evidence quote |

## Architecture

```
                   bot sentence
                        |
        +---------------+----------------+
        v                                v
  FAST LANE (regex, sub-millisecond)   does it contain a checkable claim? (cheap pre-filter)
  guarantee / urgency / threat /               |
  human-claim rules, negation-aware            v
        |                              DEEP LANE (Groq LLM)
        |                              1. extract atomic claims
        |                              2. judge each against the approved facts
        |                              3. MUST quote the fact -> otherwise UNSUPPORTED
        |                              4. every number re-checked BY CODE -> overrides the LLM
        +---------------+----------------+
                        v
         severity-weighted score + ALLOW / REWRITE / BLOCK
                        v
              compliant rewrite (same Hinglish, same intent)
```

### Design decisions worth knowing

* **Two lanes, because phone calls are latency-sensitive.** Anything decidable with code is decided with code
  (well under a millisecond per sentence: run `python -m pitchguard.bench`). Only sentences that contain a checkable
  claim go to the LLM, and that lane can run asynchronously or before an important commitment.
* **The LLM never has the last word on numbers.** Language models treat 349 and 549 as "close enough". Every number the bot
  spoke is parsed by `numbers.py` (it understands `50 lakh`, `₹8,450`, `10,00,000`, `pachaas hazaar`, `97.8%`) and compared with the cited fact.
* **No evidence, no verdict.** A SUPPORTED or CONTRADICTED verdict must quote the approved fact almost verbatim. Invented or
  paraphrased quotes are rejected and the claim becomes UNSUPPORTED (sent to human review).
* **Negation matters.** "Ye guarantee nahi hai" is a compliant sentence; a naive keyword filter would block it.
* **The model name is configuration.** Groq retires models (`llama-3.3-70b-versatile` was shut down on 16 Aug 2026).
  The default is `openai/gpt-oss-120b`; override it with `PITCHGUARD_MODEL`.
* **Results are cached on disk**, so re-running the evaluation is free and the public demo needs no API key.

## Evaluation

Two sets of synthetic calls: a **development set** (16 calls, 24 planted violations, 59 clean bot turns) that the rules and prompt were
built and tuned on, and a **held-out set** (6 calls, 4 planted violations, 27 clean bot turns) written afterwards, in my own Hinglish.

| Run | Calls | Planted violations found | Clean bot turns wrongly flagged | What changed |
|---|---|---|---|---|
| Rules only | 16 development | 15/24 (62%) | 0/59 | no LLM lane |
| Rules + Groq, v1 | 16 development | 23/24 (96%) | 10/59 (17%) | first run: conversational lines were flagged as "unsupported claims" |
| v2 | 16 development | 24/24 | 5/59 (8.5%) | prompt: statements about the conversation are not claims |
| v3 | 16 development | 24/24 | 0/59 | fixed a bug (the model wrote fact ids as `[acct.emi]`), added examples of non-claims, corrected one sample line the verifier had rightly flagged as beyond the product sheet |
| Rules only | 6 held-out | 0/4 | 0/27 | expected: these violations need the verifier |
| Rules + Groq, v3 | 6 held-out | 4/4 | 0/27 | prompt and rules frozen before this run |

Per category (development set, v3): GUARANTEE 3/3, URGENCY 2/2, PRESSURE 2/2, THREAT 1/1, AI_DISCLOSURE 2/2, PRIVACY 2/2,
MISSING_DISCLOSURE 2/2, CALL_HOURS 1/1, FALSE_CLAIM 3/3, NUMBER_MISMATCH 6/6.

**Read these numbers with care.**
* The development calls, the rules and the prompt were written together, so those figures are optimistic.
* The held-out calls were written separately, but some wording was adapted from the development set, and they cover only wrong numbers and
  invented claims (4 planted violations). A perfect score on 4 items is encouraging, not proof: the true catch rate could plausibly be much lower.
  Likewise, 0 false alarms on 27 clean turns is compatible with a true false-alarm rate of up to roughly 10%.
* The rules lane has not yet been tested on held-out calls.
* Results depend on the model; they were produced with `openai/gpt-oss-120b`.

The next step is more held-out calls written by people who have not seen the rulebook, and real transcripts.

## Run it

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q                              # 27 offline tests (number parser, rules, claim-verifier safety checks)
python -m pitchguard.evaluate --mode rules       # development set, no API key needed
streamlit run app.py                             # dashboard (works without a key)
uvicorn pitchguard.api:app --reload              # live-guard API -> POST /check
```

macOS / Linux: the same, with `source .venv/bin/activate`.

With Groq (the deep lane):

```powershell
$env:GROQ_API_KEY="gsk_..."                      # macOS / Linux: export GROQ_API_KEY=gsk_...
python -m pitchguard.evaluate --mode full        # also writes results/full/*.json for the keyless demo
python -m pitchguard.evaluate --mode full --calls data/heldout.yaml --tag _heldout
streamlit run app.py
```

Without a key, the dashboard shows the cached full results in `results/full/`; with a key it runs the verifier live.

Live guard example:

```bash
curl -X POST localhost:8000/check -H "content-type: application/json" \
  -d '{"product_id":"term_shield","scenario":"term_sales","text":"Isme 12 percent guaranteed return hai, koi risk nahi."}'
# -> {"decision":"BLOCK","violations":[{"category":"GUARANTEE",...}],"fast_lane_ms":...}
```

A voice bot would call this between "the LLM wrote the sentence" and "TTS speaks it".

## Layout

```
app.py                  Streamlit dashboard (audit a call, live guard, evaluation, how it works)
pitchguard/rules.py     fast lane + call-level rules
pitchguard/numbers.py   lakh / crore / Hindi number-word parser
pitchguard/claims.py    claim extraction, evidence + number verification, rewrites
pitchguard/guard.py     orchestration, scoring, ALLOW / REWRITE / BLOCK
pitchguard/llm.py       Groq client (retries, disk cache, model via environment variable)
pitchguard/evaluate.py  labelled-call evaluation          pitchguard/api.py  FastAPI live guard
data/                   fictional product sheets, rulebook, 16 development calls, 6 held-out calls
results/                evaluation outputs and cached full audits
tests/                  pytest suite (runs offline)
```

## Limitations and next steps

* Synthetic data, fictional products and illustrative rules. Verify against current TRAI, RBI and IRDAI text before any real use.
* Roman-script Hinglish is spelled many ways; the rule patterns need to grow with real transcripts.
* Small evaluation sets (see above).
* Next: speech-to-text confidence as a signal for mis-heard amounts, a per-customer rulebook editor, and measuring against a customer's own recordings.
