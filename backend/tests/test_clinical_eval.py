"""Run the clinical eval harness as part of the suite.

A harness nobody runs is documentation. Wiring it in means a diet template
edited six months from now cannot silently reintroduce a contradiction, and the
per-category numbers move with the code rather than with whoever remembered to
check.

Kept as thin wrappers over tools/eval_clinical so there is exactly one
definition of each check -- duplicating the logic here would just create two
things to keep in agreement.
"""
from tools import eval_clinical


def test_no_diet_advice_contradicts_the_patients_own_profile():
    """Advice that is fine in general and wrong for this patient.

    Both bugs this caught were of that shape and neither was visible reading
    the template alone: a vegetarian offered "dal, paneer, eggs, or sprouts"
    because `veg` excluded meat but not eggs, and a vegan offered "clear
    broths" because that entry carried no tags at all.
    """
    violations = eval_clinical.check_diet_consistency()
    assert not violations, "\n".join(sorted(set(violations)))


def test_every_condition_produces_usable_guidance():
    """A condition that can be diagnosed but yields no advice is a dead end."""
    gaps = eval_clinical.check_every_condition_has_guidance()
    assert not gaps, "\n".join(gaps)


def test_diagnosis_ranking_matches_the_labelled_set():
    passed, total, failures = eval_clinical.check_diagnosis()
    assert total > 0, "the labelled diagnosis set is missing or empty"
    assert not failures, "\n".join(failures)
    assert passed == total


def test_the_labelled_set_still_includes_refusals():
    """Guard against the set drifting into only-answerable cases.

    "Insufficient information" is a correct answer here, and an eval set that
    stops testing for it would let the engine become confident everywhere
    while still scoring 100%.
    """
    import yaml

    cases = yaml.safe_load(eval_clinical.DIAGNOSIS_SET.read_text(encoding="utf-8"))["cases"]
    refusals = [c for c in cases if c.get("band") == "insufficient_information"]
    assert len(refusals) >= 5, (
        f"only {len(refusals)} refusal cases; the set has drifted towards "
        "cases the engine can answer"
    )
