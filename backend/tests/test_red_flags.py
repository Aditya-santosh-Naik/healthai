"""One test per red-flag rule, plus the properties that make them worth having.

A red flag is the only part of this system that overrides everything else, so
two failure modes matter and they pull in opposite directions:

  * A rule that never fires is worse than no rule -- it looks like coverage.
    A typo in a symptom code produces exactly that, silently, because nothing
    validates the reference. Every rule below is asserted to actually escalate.
  * A rule that fires on ordinary illness makes the system cry wolf, and a
    user who learns to dismiss the banner will dismiss the real one. The
    negative cases at the bottom guard that side.
"""
import pytest

from core import knowledge, red_flags
from core.symptom_extraction import ExtractedSymptom as ES

# code -> the minimal symptom set that must trigger it.
TRIGGERS = {
    # cardiac
    "cardiac_chest_pain": ["chest_pain", "chest_pain_radiating"],
    "cardiac_chest_pain_sweating": ["chest_pain", "sweating"],
    "radiating_arm_pain": ["chest_pain_radiating"],
    "palpitations_with_fainting": ["palpitations", "fainting"],
    "atypical_cardiac_presentation": ["jaw_pain", "shortness_of_breath"],
    # respiratory
    "cyanosis": ["blue_lips"],
    "cannot_complete_sentences": ["unable_to_speak_sentences"],
    "breathless_at_rest": ["breathlessness_at_rest"],
    "coughing_blood": ["blood_in_sputum"],
    # neurological
    "stroke_signs": ["sudden_weakness_one_side"],
    "seizure": ["seizures"],
    "sudden_vision_loss": ["vision_loss"],
    "thunderclap_headache": ["severe_headache", "vomiting"],
    "fainting_episode": ["fainting"],
    "meningitis_signs": ["stiff_neck", "high_fever"],
    # sepsis
    "sepsis_fever_confusion": ["high_fever", "confusion"],
    "sepsis_fever_rapid_breathing": ["fever", "rapid_breathing"],
    "sepsis_poor_perfusion": ["fever", "cold_hands_feet"],
    "sepsis_low_urine_output": ["fever", "low_urine_output"],
    # anaphylaxis
    "anaphylaxis_breathing": ["rash", "shortness_of_breath"],
    "anaphylaxis_airway": ["itching", "unable_to_speak_sentences"],
    # gastrointestinal
    "black_stools_flag": ["black_stools"],
    "vomiting_blood_flag": ["blood_in_vomit"],
    "peritonitis_signs": ["severe_abdominal_pain", "abdominal_tenderness"],
    "severe_abdominal_pain_flag": ["severe_abdominal_pain"],
    "persistent_vomiting_flag": ["persistent_vomiting"],
    # other
    "severe_dehydration_flag": ["severe_dehydration"],
    "jaundice": ["yellow_eyes"],
}


def reported(*codes: str):
    return [ES(code=c, present=True) for c in codes]


@pytest.mark.parametrize(
    "rule,codes",
    sorted(TRIGGERS.items()),
    ids=[c for c in sorted(TRIGGERS)],
)
def test_each_trigger_set_escalates(rule, codes):
    assert red_flags.check(reported(*codes)) is not None, (
        f"{rule}: {codes} did not escalate; the rule is present but unreachable"
    )


def test_an_implied_parent_still_satisfies_a_rule():
    """Regression: `meningitis_signs` is all_of [fever, stiff_neck], so
    "high fever and a stiff neck" only matches once high_fever expands to
    fever. That expansion used to happen only in extraction, so the rule
    worked through the pipeline and failed for every other caller."""
    assert red_flags.check(reported("high_fever", "stiff_neck")) is not None


def test_every_rule_references_symptoms_that_exist():
    """A typo makes a rule that can never fire, and nothing else catches it."""
    vocabulary = set(knowledge.symptoms())
    unknown = [
        (flag.code, code)
        for flag in knowledge.red_flags()
        for code in list(flag.any_of) + list(flag.all_of)
        if code not in vocabulary
    ]
    assert not unknown, f"rules reference symptoms that do not exist: {unknown}"


def test_every_rule_carries_a_source():
    """Invariant 5. An unsourced escalation is an assertion, not encoded guidance."""
    unsourced = [f.code for f in knowledge.red_flags() if not getattr(f, "source_url", "")]
    assert not unsourced, unsourced


def test_the_categories_the_spec_asks_for_are_all_covered():
    codes = {f.code for f in knowledge.red_flags()}
    for label, needle in [
        ("cardiac", "cardiac"),
        ("sepsis", "sepsis"),
        ("anaphylaxis", "anaphylaxis"),
        ("stroke", "stroke"),
        ("dengue", "dengue"),
        ("dehydration", "dehydration"),
    ]:
        assert any(needle in c for c in codes), f"no {label} red flag"


def test_there_are_at_least_thirty_rules():
    assert len(knowledge.red_flags()) >= 30


# --- the other direction: ordinary illness must NOT escalate ----------------

@pytest.mark.parametrize(
    "codes",
    [
        ["fever", "cough"],
        ["runny_nose", "sneezing", "sore_throat"],
        ["headache"],
        ["fever", "body_ache", "chills"],
        ["diarrhoea", "abdominal_cramps"],
        ["heartburn", "sour_taste"],
        ["cough", "dry_cough", "fatigue"],
        ["nausea", "loss_of_appetite"],
    ],
)
def test_ordinary_illness_does_not_escalate(codes):
    """Crying wolf has a cost: a user who learns to dismiss the banner will
    dismiss the one that matters."""
    assert red_flags.check(reported(*codes)) is None, (
        f"{codes} escalated -- this is an everyday presentation"
    )


def test_a_denied_red_flag_symptom_does_not_escalate():
    """Answering "no" to a screening question must not trigger the thing it
    was screening for. Presence is tri-state and only True counts."""
    assert red_flags.check([ES(code="chest_pain", present=False)]) is None
    assert red_flags.check([ES(code="blue_lips", present=False)]) is None


def test_an_unknown_answer_does_not_escalate():
    """"Not sure" is not a report. Escalating on it would fabricate a finding."""
    assert red_flags.check([ES(code="blue_lips", present=None)]) is None
    assert red_flags.check([ES(code="seizures", present=None)]) is None
