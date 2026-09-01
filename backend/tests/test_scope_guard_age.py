"""Age stated in text, not just in the profile.

Spec invariant 9 refuses under-18s. The profile age enforces that for anyone
using their own account. The case it cannot see is a child on somebody else's
account -- a parent's phone, a shared family login -- where the profile says 48
and the person typing is 14. Every existing paediatric pattern is
third-person ("my son", "my 12-year-old"), so first-person went straight
through.
"""
import pytest

from core import scope_guard as sg

ADULT_PROFILE = 48


@pytest.mark.parametrize(
    "text",
    [
        "i am 14 years old and have fever",
        "im 15 and have a cough",
        "i am 16, fever since 2 days",
        "i am only 12",
        "my age is 13",
        "aged 17 with sore throat",
        "15 year old boy with fever",
        "i'm 11 and my stomach hurts",
    ],
)
def test_a_minor_stating_their_own_age_is_refused(text):
    result = sg.check(text, ADULT_PROFILE)
    assert result is not None, "a minor was assessed"
    assert result.category == "under_18"
    assert result.referral


@pytest.mark.parametrize(
    "text",
    [
        "i am 45 and have fever",
        "i am 30 years old with a headache",
        "i am 18 and have fever",
        # Durations that contain a number small enough to look like a child's age.
        "i have had this cough for 14 years",
        "fever for 3 years now",
        "pain for 2 days",
        "this started 10 days ago",
        "i have had 3 episodes of vomiting",
    ],
)
def test_adults_and_durations_are_not_refused(text):
    """Over-refusing is its own failure: it makes the tool useless for the
    people it is for, and a duration is not an age."""
    assert sg.check(text, ADULT_PROFILE) is None, f"{text!r} was wrongly refused"


def test_a_stated_age_overrides_the_profile_only_downwards():
    """An adult age in the text must not unlock a profile that says 12.

    Otherwise the guard is trivially bypassed by typing "I am 30".
    """
    assert sg.check("i am 30 and have fever", 12) is not None
    assert sg.check("i am 14 and have fever", 48) is not None
    assert sg.check("i have fever", 48) is None


def test_the_youngest_stated_age_wins():
    """Several numbers in one message: take the reading that refuses."""
    assert sg.stated_age("i am 40, my age is 15") == 15


def test_stated_age_ignores_implausible_numbers():
    assert sg.stated_age("i am 0") is None
    assert sg.stated_age("i have had fever 99 times") is None
