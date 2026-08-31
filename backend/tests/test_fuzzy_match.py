"""Spelling repair, and the line it must not cross.

Recall and precision are not symmetric here. A missed symptom produces a
follow-up question; a fabricated one produces a fabricated assessment. Every
test below that starts "does not" is guarding the second case, and those matter
more than the ones checking a repair works.
"""
import pytest

from core import fuzzy_match
from core.symptom_extraction import extract


def codes(text: str) -> set[str]:
    return {s.code for s in extract(text) if s.present is True}


def denied(text: str) -> set[str]:
    return {s.code for s in extract(text) if s.present is False}


# --- repairs that must happen -----------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("i have fewer", "fever"),
        ("vometing since morning", "vomiting"),
        ("vomitting a lot", "vomiting"),
        ("hedache", "headache"),
        ("stomac pain", "abdominal_pain"),
        ("diarhea", "diarrhoea"),
        ("brething problem", "shortness_of_breath"),
    ],
)
def test_misspellings_reach_the_right_symptom(text, expected):
    assert expected in codes(text), f"{text!r} did not repair to {expected}"


def test_fewer_is_repaired_even_though_it_is_a_real_word():
    """The case a general spellchecker cannot handle.

    "fewer" is correctly spelled, so a dictionary passes it through untouched
    and the extractor sees no fever. Correction has to be biased towards the
    medical vocabulary to catch it.
    """
    assert "fever" in codes("i have fewer and cough")


# --- repairs that must NOT happen -------------------------------------------

@pytest.mark.parametrize(
    "word",
    ["never", "every", "other", "water", "worse", "later", "sleep", "please"],
)
def test_common_words_are_never_rewritten(word):
    assert fuzzy_match.repair(word) == word


def test_a_denial_is_not_turned_into_a_symptom():
    """`never` sits the same edit distance from `fever` as `fewer` does.

    Without the protected list it repairs identically, and "never had fever"
    becomes a reported fever -- a fabricated symptom sourced from a denial.
    """
    assert "fever" not in codes("i never had fever")
    assert "fever" in denied("i never had fever")


def test_contractions_survive_repair():
    """Regression: [A-Za-z]+ split "haven't" into "haven" + "t", "haven"
    repaired to "havent", and the resulting "havent't" was no longer
    recognised as a negation -- a denied fever read as a reported one."""
    assert "fever" in denied("runny nose and sneezing, haven't had any fever")
    assert "'" in fuzzy_match.repair("haven't")


def test_an_ambiguous_token_is_left_alone():
    """A token near two DIFFERENT symptoms is a guess, so it is not made."""
    # Nonsense that is not close to anything must pass through untouched.
    for junk in ["qwertyuiop", "zzzzzz", "asdfgh"]:
        assert fuzzy_match.repair(junk) == junk


def test_near_synonyms_of_the_same_symptom_are_not_treated_as_ambiguous():
    """The fix that unlocked most of the recall gain.

    "vometing" sits between "vomiting" and "vomitings". Judged as strings that
    is a tie and the repair was abandoned; judged by MEANING both are the same
    symptom and there is nothing to be ambiguous about.
    """
    assert "vomiting" in codes("vometing since yesterday")


def test_numbers_and_short_tokens_are_untouched():
    assert fuzzy_match.repair("2din") == "2din"
    assert fuzzy_match.repair("3 day") == "3 day"


# --- code-mixed input --------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("jwar aur khansi", {"fever", "cough"}),
        ("pet dard", {"abdominal_pain"}),
        ("tale novu", {"headache"}),
        ("vayiru vali", {"abdominal_pain"}),
        ("chakkar aa raha hai", {"dizziness"}),
        ("kamzori", {"weakness"}),
    ],
)
def test_code_mixed_terms_extract(text, expected):
    assert expected <= codes(text), f"{text!r} missed {expected - codes(text)}"


def test_postfix_negation_is_understood():
    """Hindi puts the negator last: "khansi nahi" is "cough not".

    A forward-only scope model reads that as a reported cough.
    """
    result = extract("fever hai but khansi nahi")
    assert "fever" in {s.code for s in result if s.present is True}
    assert "cough" in {s.code for s in result if s.present is False}
