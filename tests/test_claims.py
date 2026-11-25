"""The LLM lane is tested with a fake model, so these run offline and prove the SAFETY CHECKS work."""
from pitchguard.claims import check_claims, quote_in_fact
from pitchguard.kb import load_products

FACTS = load_products()["term_shield"].facts


class Fake:
    def __init__(self, claims):
        self.claims = claims

    def complete_json(self, system, user, max_tokens=0):
        return {"claims": self.claims}


def run(claims, utterance):
    return check_claims(utterance, [], FACTS, Fake(claims))


def test_number_check_overrides_a_lazy_supported_verdict():
    u = "50 lakh ka cover sirf 349 rupaye mahine mein mil jayega"
    v = run([{"span": "sirf 349 rupaye mahine", "claim": "premium is 349/month", "verdict": "SUPPORTED",
              "fact_id": "term.premium", "evidence": "Illustrative premium: ₹549 per month"}], u)
    assert [x.category for x in v] == ["NUMBER_MISMATCH"]


def test_correct_number_passes():
    u = "30 saal ke non-smoker ke liye 549 rupaye mahine se shuru"
    v = run([{"span": "549 rupaye mahine", "claim": "premium 549", "verdict": "SUPPORTED",
              "fact_id": "term.premium", "evidence": "₹549 per month for ₹50 lakh cover"}], u)
    assert v == []


def test_invented_evidence_is_downgraded_to_unsupported():
    u = "Isme free health checkup milta hai"
    v = run([{"span": u, "claim": "free checkup", "verdict": "SUPPORTED", "fact_id": "term.riders",
              "evidence": "Free annual health checkup is included"}], u)
    assert [(x.category, x.severity) for x in v] == [("FALSE_CLAIM", "medium")]


def test_contradiction_with_real_quote_is_high_severity():
    u = "Isme free health checkup milta hai"
    v = run([{"span": u, "claim": "free checkup", "verdict": "CONTRADICTED", "fact_id": "term.riders",
              "evidence": "No health checkup or hospital cover is included in the base plan"}], u)
    assert [(x.category, x.severity) for x in v] == [("FALSE_CLAIM", "high")]


def test_span_that_is_not_in_the_utterance_falls_back_safely():
    u = "Claim settlement ratio 97.8 percent hai"
    v = run([{"span": "something the bot never said", "claim": "x", "verdict": "SUPPORTED", "fact_id": "term.claims",
              "evidence": "Claim settlement ratio for FY 2025-26 was 97.8%"}], u)
    assert v == []


def test_quote_checker():
    assert quote_in_fact("97.8% (illustrative", "Claim settlement ratio for FY 2025-26 was 97.8% (illustrative figure)")
    assert not quote_in_fact("hospital cover included free", "No health checkup or hospital cover is included in the base plan.")

def test_fact_id_with_brackets_is_accepted():
    u = "30 saal ke non-smoker ke liye 549 rupaye mahine se shuru"
    v = run([{"span": "549 rupaye mahine", "claim": "premium 549", "verdict": "SUPPORTED",
              "fact_id": "[term.premium]", "evidence": "₹549 per month for ₹50 lakh cover"}], u)
    assert v == []