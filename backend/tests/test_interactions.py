"""Interaction and contraindication coverage.

The spec calls medication safety the most clinically valuable feature, and it
has a quiet failure mode: a rule that reads correctly in YAML but can never
match anything. Rules are keyed on generic names, patients type brand names,
combination products have to expand to their parts, and lifestyle factors live
somewhere else entirely. Any of those breaks silently -- the safety block just
shows nothing and looks like a clean bill of health.
"""
import pytest

from core import knowledge, medication_safety as ms
from core.patient_context import ProfileFacts


def report(meds, conditions=(), allergies=(), symptoms=()):
    return ms.evaluate(list(meds), list(allergies), list(conditions), set(symptoms))


def reasons(rep):
    return " ".join(f.reason.lower() for f in rep.findings)


# --- the rules must be reachable at all -------------------------------------

def test_every_rule_names_a_drug_the_system_can_resolve():
    """A subject the resolver does not know is a rule that never fires."""
    known = set()
    for entry in knowledge.drugs().values():
        known.add(entry.generic)
        # Combination products expand to their parts, so a rule keyed on
        # "ibuprofen" legitimately applies to "ibuprofen+paracetamol".
        known.update(part.strip() for part in entry.generic.split("+"))
    unknown = sorted({r.subject for r in knowledge.interactions() if r.subject not in known})
    assert not unknown, f"rules keyed on unresolvable drugs: {unknown}"


def test_every_rule_carries_a_source():
    unsourced = [
        f"{r.subject} x {r.object}"
        for r in knowledge.interactions()
        if not getattr(r, "source_url", "")
    ]
    assert not unsourced, unsourced


def test_there_are_at_least_eighty_rules():
    assert len(knowledge.interactions()) >= 80


# --- lifestyle factors ------------------------------------------------------

def test_alcohol_reaches_the_drug_condition_check():
    """Alcohol is a boolean on the profile, not an entry in the condition list.

    Before ProfileFacts.safety_conditions existed, a rule written against it
    was unreachable -- metronidazole with alcohol causes a genuinely nasty
    reaction and there was no way to express it.
    """
    facts = ProfileFacts(alcohol=True, conditions=["Hypertension"])
    assert "alcohol use" in facts.safety_conditions
    assert "Hypertension" in facts.safety_conditions

    rep = report(
        [{"brand_name": "Metrogyl", "generic_name": "metronidazole"}],
        conditions=facts.safety_conditions,
    )
    assert any(f.severity == "avoid" for f in rep.findings)
    assert "alcohol" in reasons(rep)


def test_lifestyle_factors_are_not_phrased_as_diagnoses():
    """"You take Metrogyl and have alcohol use" is ungrammatical and, worse,
    tells the patient something untrue about their medical record."""
    rep = report(
        [{"brand_name": "Metrogyl", "generic_name": "metronidazole"}],
        conditions=["alcohol use"],
    )
    text = reasons(rep)
    assert "drink alcohol" in text
    assert "have alcohol use" not in text


def test_a_teetotal_non_smoker_gets_neither_factor():
    facts = ProfileFacts(alcohol=False, smoker=False, conditions=["GERD"])
    assert facts.safety_conditions == ["GERD"]


def test_lifestyle_factors_stay_out_of_the_displayed_condition_list():
    """`conditions` is for display, `safety_conditions` for matching. Mixing
    them would put "alcohol use" in the doctor summary as a diagnosis."""
    facts = ProfileFacts(alcohol=True, smoker=True, conditions=["Asthma"])
    assert facts.conditions == ["Asthma"]


# --- previously uncovered drugs ---------------------------------------------

@pytest.mark.parametrize(
    "generic,conditions,expect",
    [
        ("metronidazole", ["alcohol use"], "avoid"),
        ("rosuvastatin", ["liver disease"], "caution"),
        ("glibenclamide", ["alcohol use"], "caution"),
        ("cetirizine", ["kidney disease"], "caution"),
        ("cefixime", ["kidney disease"], "caution"),
        ("amoxicillin", ["kidney disease"], "caution"),
        ("domperidone", ["heart disease"], "avoid"),
        ("montelukast", ["depression"], "caution"),
    ],
)
def test_drugs_that_previously_had_no_rules_now_produce_findings(
    generic, conditions, expect
):
    rep = report([{"generic_name": generic}], conditions=conditions)
    severities = {f.severity for f in rep.findings}
    assert expect in severities, f"{generic} x {conditions} produced {severities or 'nothing'}"


def test_a_statin_and_a_macrolide_are_flagged_together():
    rep = report([{"generic_name": "rosuvastatin"}, {"generic_name": "clarithromycin"}])
    assert any(f.severity == "avoid" and f.kind == "drug_drug" for f in rep.findings)


# --- the existing behaviour must not regress --------------------------------

def test_a_healthy_patient_on_nothing_gets_no_findings():
    rep = report([])
    assert rep.findings == []


def test_an_ordinary_pairing_is_still_clean():
    """Over-flagging is its own failure: a safety block that always shows
    something teaches the patient to skip it."""
    rep = report([{"generic_name": "paracetamol"}], conditions=["Hypertension"])
    assert not [f for f in rep.findings if f.severity == "avoid"]
