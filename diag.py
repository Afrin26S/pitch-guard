import json
from pitchguard import claims
from pitchguard.kb import load_calls, load_products
from pitchguard.llm import get_llm

llm = get_llm()
calls = {c.id: c for c in load_calls()}
products = load_products()
targets = [("c01_clean", 2), ("c01_clean", 4), ("l01_clean", 10),
           ("l02_approval_promise", 2), ("l04_pressure", 2)]

for cid, i in targets:
    c = calls[cid]
    facts = products[c.product].facts + c.account_facts
    ctx = [f"{x.speaker.upper()}: {x.text}" for x in c.turns[max(0, i - 2):i]]
    ctx_txt = "\n".join(ctx[-2:]) or "(start of call)"
    user = (f"APPROVED FACTS:\n{claims._facts_block(facts)}\n\n"
            f"RECENT CONTEXT:\n{ctx_txt}\n\nBOT UTTERANCE:\n{c.turns[i].text}")
    raw = llm.complete_json(claims.SYSTEM, user)
    print(f"--- {cid} turn {i}: {c.turns[i].text}")
    print(json.dumps(raw, ensure_ascii=False, indent=1))