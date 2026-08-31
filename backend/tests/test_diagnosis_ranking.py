"""Ranking regressions for the evidence engine.

These run against the engine directly rather than through the API. The thing
under test is the ORDER candidates come out in and why, which the HTTP layer
only obscures -- and going direct keeps them fast enough to run on every edit.

The failure they exist to prevent: an engine with no prevalence prior and no
notion of how much a symptom discriminates, which ranked on symptom-list
membership alone.
"""
import pytest

from core import evidence_engine as ee
from core.evidence_engine import BASE_RATE_PRIOR, Band
from core.symptom_extraction import extract


def rank(text: str) -> tuple[list, str]:
    results, band = ee.evaluate(extract(text))
    return results, band


def position(results, code: str) -> int:
    for i, result in enumerate(results):
        if result.code == code:
            return i
    raise AssertionError(f"{code} missing from results")


def score_of(results, code: str) -> float:
    return results[position(results, code)].score


# --- the six cases from the hotfix spec -------------------------------------

def test_bare_cough_prefers_the_common_cold_over_influenza():
    """A cough on its own is a cold far more often than it is flu."""
    results, _ = rank("cough")
    assert score_of(results, "common_cold") > score_of(results, "influenza")


def test_bare_sore_throat_does_not_lead_to_influenza():
    """Sore throat is a cold or a strep throat long before it is flu."""
    results, _ = rank("sore throat")
    assert score_of(results, "influenza") < max(
        score_of(results, "common_cold"), score_of(results, "strep_pharyngitis")
    )


def test_a_full_influenza_picture_ranks_influenza_first():
    results, _ = rank("fever, body aches, chills, sudden onset, dry cough, 2 days")
    assert results[0].code == "influenza"


def test_specific_evidence_overrides_a_lower_base_rate():
    """The point of the whole exercise.

    Dengue is `uncommon` and starts four points behind a cold. Retro-orbital
    pain appears in exactly one condition, so it carries the maximum
    specificity weight, and it must be able to win outright. If this test ever
    fails, the priors have grown too strong or the specificity clamp too low,
    and over-diagnosis has simply been traded for under-diagnosis.
    """
    results, _ = rank("high fever, severe headache, pain behind eyes, severe body ache")
    assert results[0].code == "dengue"
    assert BASE_RATE_PRIOR["uncommon"] < BASE_RATE_PRIOR["very_common"]


def test_diarrhoea_without_a_food_history_leads_to_gastroenteritis():
    """Food poisoning is defined by the exposure, so absent it, the general
    diagnosis leads. These two tied exactly before `outside_food` became an
    expected symptom of food poisoning."""
    results, _ = rank("loose motions 2 days, stomach ache")
    assert results[0].code == "gastroenteritis"
    assert position(results, "food_poisoning") == 1
    assert score_of(results, "typhoid") < score_of(results, "food_poisoning")


def test_bare_fever_names_nothing():
    _, band = rank("fever")
    assert band == Band.INSUFFICIENT


# --- properties the recalibration depends on --------------------------------

def test_prevalence_alone_never_makes_a_candidate_possible():
    """The anchor the band cutoffs were chosen against.

    POSSIBLE_MIN_SCORE must stay above the largest prior, or the four
    `very_common` conditions would qualify as 'possible' on prevalence with no
    evidence at all -- naming a cold for every consultation.
    """
    assert ee.POSSIBLE_MIN_SCORE > max(BASE_RATE_PRIOR.values())


@pytest.mark.parametrize("tier", ["very_common", "common", "uncommon", "rare"])
def test_every_prior_tier_is_used_by_at_least_one_condition(tier):
    from core import knowledge

    assert any(c.base_rate == tier for c in knowledge.conditions().values()), (
        f"no condition uses the {tier} tier -- the table has drifted from the data"
    )


def test_every_condition_declares_a_prior_and_its_provenance():
    from core import knowledge

    for condition in knowledge.conditions().values():
        assert condition.base_rate in BASE_RATE_PRIOR, condition.code
        assert condition.base_rate_source, f"{condition.code} has no base_rate_source"


def test_specificity_is_bounded_and_a_generic_symptom_is_worth_less():
    """Unclamped IDF lets one rare symptom outweigh three hallmarks."""
    from core import specificity

    weights = specificity.compute()
    assert weights, "no specificity weights computed"
    assert all(
        specificity.MIN_WEIGHT <= w <= specificity.MAX_WEIGHT for w in weights.values()
    )
    # `fever` is shared far more widely than retro-orbital pain, so it must
    # carry less weight. Asserting the relationship rather than the numbers,
    # which move whenever a condition is added.
    assert weights["fever"] < weights["retro_orbital_pain"]


def test_specificity_weights_are_not_piled_against_the_ceiling():
    """The weights must actually discriminate, not just rescale.

    The clamped form saturated: 50 of 63 symptoms sat exactly on the 2.0 cap,
    so four fifths of the vocabulary shared one weight and the multiplier was
    close to a uniform x2. Only symptoms unique to a single condition should
    reach the ceiling.
    """
    from core import knowledge, specificity

    weights = specificity.compute()
    conditions = knowledge.conditions()
    at_ceiling = [c for c, w in weights.items() if w >= specificity.MAX_WEIGHT - 1e-9]

    assert len(at_ceiling) < len(weights) / 2, (
        f"{len(at_ceiling)} of {len(weights)} weights are at the ceiling; the "
        "weighting has saturated and is no longer discriminating"
    )
    for code in at_ceiling:
        n = sum(1 for cond in conditions.values() if code in cond.all_symptoms)
        assert n == 1, f"{code} is in {n} conditions but scores the maximum weight"


def test_a_symptom_in_more_conditions_never_scores_higher():
    """The weight must be monotone in how widely a symptom is shared."""
    from core import knowledge, specificity

    weights = specificity.compute()
    conditions = knowledge.conditions()
    counts = {
        code: sum(1 for c in conditions.values() if code in c.all_symptoms)
        for code in weights
    }
    ordered = sorted(weights, key=lambda code: counts[code])
    for earlier, later in zip(ordered, ordered[1:]):
        if counts[earlier] < counts[later]:
            assert weights[earlier] >= weights[later], (
                f"{earlier} (in {counts[earlier]}) scores less than "
                f"{later} (in {counts[later]})"
            )
