import pytest

from pitchguard.kb import load_rulebook
from pitchguard.rules import check_turn

RB = load_rulebook()


def cats(text, scenario="term_sales"):
    return {v.category for v in check_turn(text, scenario, RB)}


@pytest.mark.parametrize("text", [
    "Isme har saal 12 percent guaranteed return milta hai.",
    "Ye bilkul risk-free hai.",
    "Aapka loan pakka approve ho jayega.",
    "Isme koi risk nahi hai.",
    "आपका लोन पक्का अप्रूव हो जाएगा",
])
def test_guarantee_language_is_flagged(text):
    assert "GUARANTEE" in cats(text)


@pytest.mark.parametrize("text", [
    "Ye future ke liye guarantee nahi hai.",
    "Main approval ki guarantee nahi de sakti.",
    "This is not guaranteed.",
    "Returns guaranteed nahi hote.",
])
def test_negated_guarantee_is_allowed(text):
    assert "GUARANTEE" not in cats(text)


def test_urgency_and_pressure():
    c = cats("Ye offer sirf aaj ke liye hai. Abhi decide kar lijiye.")
    assert {"URGENCY", "PRESSURE"} <= c


def test_no_false_urgency_on_normal_scheduling():
    assert cats("Main kal subah 11 baje callback schedule kar deti hoon.") == set()


def test_threat_only_matters_in_collections_wording():
    assert "THREAT" in cats("Hum police ko bhejenge aur ghar walon ko bata denge.", "collections")
    assert "THREAT" not in cats("Aap Udaan app se payment kar sakti hain.", "collections")


def test_claims_to_be_human():
    assert "AI_DISCLOSURE" in cats("Nahi sir, main ek real insaan hoon, robot nahi hoon.")
