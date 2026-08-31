"""Bounds on everything a patient can type into their profile.

Two different jobs are being done here and they should not be confused:

  * **Data integrity** -- age 1-122, plausible height and weight, a real blood
    group, non-blank names, no future dates. These reject typos and probes.
  * **Clinical scope** -- under-18 is refused, but at the scope guard on every
    consultation, not here. See
    test_day1_foundation.test_under_18_can_register_but_is_refused_a_consultation.

Validation is not a safety layer, and pretending otherwise is how a clinical
rule ends up enforced once at signup and bypassable by editing a profile later.
"""
import pytest

from schemas.profile import MAX_AGE, MAX_LIST_ITEMS, MIN_AGE
from tests.test_day1_foundation import VALID_PROFILE, auth, client, register  # noqa: F401


def post_profile(client, token, **overrides):
    return client.post(
        "/api/profile", json={**VALID_PROFILE, **overrides}, headers=auth(token)
    )


# --- age --------------------------------------------------------------------

@pytest.mark.parametrize("age", [MIN_AGE, 18, 45, 100, MAX_AGE])
def test_plausible_ages_are_accepted(client, age):
    token = register(client, email=f"age{age}@example.com")
    assert post_profile(client, token, age=age).status_code == 201


@pytest.mark.parametrize("age", [0, -1, -100, MAX_AGE + 1, 150, 999, 100000])
def test_impossible_ages_are_rejected(client, age):
    """122 is the oldest verified human lifespan (Jeanne Calment). Above it is
    a typo or a probe, not a patient."""
    token = register(client, email=f"bad{abs(age)}@example.com")
    assert post_profile(client, token, age=age).status_code == 422


@pytest.mark.parametrize("age", ["forty", None, 45.7, "", []])
def test_non_integer_ages_are_rejected(client, age):
    token = register(client)
    assert post_profile(client, token, age=age).status_code == 422


# --- height and weight ------------------------------------------------------

@pytest.mark.parametrize(
    "field,value",
    [
        ("height_cm", 10),      # decimal point slipped
        ("height_cm", 0),
        ("height_cm", -170),
        ("height_cm", 500),
        ("weight_kg", 0.4),
        ("weight_kg", 0),
        ("weight_kg", -70),
        ("weight_kg", 900),
    ],
)
def test_impossible_body_measurements_are_rejected(client, field, value):
    token = register(client)
    assert post_profile(client, token, **{field: value}).status_code == 422


def test_height_and_weight_stay_optional(client):
    token = register(client)
    r = post_profile(client, token, height_cm=None, weight_kg=None)
    assert r.status_code == 201


# --- blood group ------------------------------------------------------------

@pytest.mark.parametrize("group", ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"])
def test_the_eight_real_blood_groups_are_accepted(client, group):
    token = register(client, email=f"bg{group.replace('+', 'p').replace('-', 'm')}@example.com")
    assert post_profile(client, token, blood_group=group).status_code == 201


@pytest.mark.parametrize("group", ["XYZ", "C+", "A", "+", "O++", "AB", "1234", "O positive"])
def test_invented_blood_groups_are_rejected(client, group):
    """Free text here ends up on a document a doctor might read."""
    token = register(client)
    assert post_profile(client, token, blood_group=group).status_code == 422


def test_blood_group_case_is_normalised(client):
    token = register(client)
    r = post_profile(client, token, blood_group="  ab-  ")
    assert r.status_code == 201
    assert r.json()["blood_group"] == "AB-"


# --- names ------------------------------------------------------------------

@pytest.mark.parametrize("name", ["", "   ", "\t", "\n  \n"])
def test_blank_names_are_rejected(client, name):
    """min_length=1 alone lets a single space through."""
    token = register(client)
    assert post_profile(client, token, name=name).status_code == 422


def test_names_are_trimmed(client):
    token = register(client)
    r = post_profile(client, token, name="  Asha Menon  ")
    assert r.status_code == 201
    assert r.json()["name"] == "Asha Menon"


def test_an_overlong_name_is_rejected(client):
    token = register(client)
    assert post_profile(client, token, name="x" * 500).status_code == 422


# --- dates ------------------------------------------------------------------

def test_a_future_onset_date_is_rejected(client):
    token = register(client)
    r = post_profile(
        client,
        token,
        conditions=[{"condition_name": "Asthma", "onset_date": "2099-01-01"}],
    )
    assert r.status_code == 422


def test_a_future_medication_start_date_is_rejected(client):
    token = register(client)
    r = post_profile(
        client,
        token,
        medications=[{"brand_name": "Dolo 650", "start_date": "2099-01-01"}],
    )
    assert r.status_code == 422


# --- related lists ----------------------------------------------------------

def test_a_medication_with_no_name_at_all_is_rejected(client):
    """It would sit in the profile looking recorded while the interaction
    check has nothing to resolve -- and the safety block would still claim to
    have checked it."""
    token = register(client)
    r = post_profile(client, token, medications=[{"dose": "500mg", "frequency": "BD"}])
    assert r.status_code == 422


def test_a_generic_name_alone_is_enough(client):
    token = register(client)
    r = post_profile(client, token, medications=[{"generic_name": "paracetamol"}])
    assert r.status_code == 201


def test_absurdly_long_lists_are_rejected(client):
    """One request must not be able to write unbounded rows."""
    token = register(client)
    many = [{"condition_name": f"Condition {i}"} for i in range(MAX_LIST_ITEMS + 1)]
    assert post_profile(client, token, conditions=many).status_code == 422


def test_a_blank_condition_name_is_rejected(client):
    token = register(client)
    r = post_profile(client, token, conditions=[{"condition_name": "   "}])
    assert r.status_code == 422
