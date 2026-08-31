"""Spelling repair against the MEDICAL vocabulary. Supports pipeline step 2.

A general spellchecker is the wrong tool here, and "fewer" is the example that
proves it: it is a correctly spelled English word, so a dictionary leaves it
alone, and the extractor then finds no fever. Correction has to be biased
towards the vocabulary the system actually reasons about.

The design constraint that shapes everything below: **this must never invent a
symptom the patient did not state.** A missed symptom leads to a follow-up
question. A fabricated one leads to a fabricated assessment. The two failures
are not comparable, so every rule here is tuned to be conservative and the
evaluation tracks forbidden false positives separately from recall -- recall
may improve, false positives must stay at zero.

Three guards make that concrete:

  1. Only tokens that are NOT already vocabulary words are considered. A word
     the vocabulary knows is never second-guessed.
  2. A stoplist of frequent English words is never corrected, however close.
     Without it "never" corrects to "fever" as readily as "fewer" does -- the
     edit distance is identical -- and a denial becomes a symptom.
  3. A correction must be clearly better than the runner-up. If two vocabulary
     words are near-equally close, the token is left alone rather than guessed
     at.
"""
import re
from difflib import SequenceMatcher
from functools import lru_cache

from core import knowledge
from core.text_norm import STOPWORDS

# How similar a token must be to a vocabulary word before it is rewritten.
# Tuned against both eval sets, not chosen a priori. 0.72 admits fewer->fever
# (0.80) and feavor->fever (0.73); the ambiguity rule below, not this floor, is
# what keeps false positives at zero, so the floor can afford to be generous.
SIMILARITY_FLOOR = 0.72

# The best match must beat the runner-up by this much -- but only a runner-up
# meaning something DIFFERENT. See _codes_for.
MARGIN = 0.06

# Below this length, edit distance stops discriminating: three-letter tokens
# are within one edit of half the vocabulary.
MIN_TOKEN_LENGTH = 4

# Frequent English words that sit close to a symptom term. Correcting any of
# these silently converts ordinary prose into a clinical claim, and "never"
# and "not" would turn a denial into a report.
PROTECTED = frozenset(
    """
    never ever every over other under after before around here there where
    when what which while whole worse worst felt feel feels fell full fall
    call tall wall well will well since start started stop stopped
    take taken takes make makes made made give given gives
    come comes came goes gone going does done doing
    much many more most less least last late later
    also although always almost about above below
    said says tell told talk help please thanks doctor
    water food sleep work home night morning evening today yesterday
    week weeks month months year years day days hour hours time times
    little lot lots very really quite bit
    something anything nothing everything someone anyone everyone
    thing things stuff kind sort like
    """.split()
) | STOPWORDS
# STOPWORDS are folded in because canonicalisation strips them, so they never
# reach `vocabulary()` and would otherwise look like unknown words worth
# repairing -- "with" is four letters and one edit from several symptom terms.

# Contraction-aware on purpose. A bare [A-Za-z]+ splits "haven't" into
# "haven" + "t", and "haven" is then five letters from "havent" -- the repair
# produced "havent't", the contraction expander no longer recognised it, and a
# denied fever was read as a reported one. A fabricated symptom from a DENIAL
# is the worst failure this module can produce.
_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")


@lru_cache(maxsize=1)
def _word_codes() -> dict[str, frozenset[str]]:
    """Every alias word, mapped to the symptom codes it can belong to.

    The codes are the point. Ambiguity has to be judged on MEANING, not
    spelling: "vomiting" and "vomitings" are near-identical strings and both
    lead to the same symptom, so a token sitting between them is not ambiguous
    at all. Comparing words alone rejected exactly the repairs this module
    exists to make -- vometing, vomitting and diarhea were all thrown away for
    being too close to a synonym of the right answer.
    """
    words: dict[str, set[str]] = {}
    for alias, code in knowledge.alias_index():
        for part in alias.split():
            # PROTECTED words are excluded as TARGETS as well as being
            # exempt from correction. Some ordinary prose leaks into the
            # vocabulary through multi-word aliases -- "something" arrives via
            # a postnasal-drip alias -- and as a candidate it then blocks
            # genuine repairs by looking like a rival meaning: "vometing" is
            # 0.824 from "something" and 0.875 from "vomiting", close enough
            # to be called ambiguous and abandoned. A repair target has to be
            # a distinctive clinical token.
            if len(part) >= MIN_TOKEN_LENGTH and part not in PROTECTED:
                words.setdefault(part, set()).add(code)
    return {word: frozenset(codes) for word, codes in words.items()}


@lru_cache(maxsize=1)
def vocabulary() -> frozenset[str]:
    """Every single word appearing in any symptom alias.

    Multi-word aliases are split: "loose motions" contributes both "loose" and
    "motions", so "loose motionn" repairs to something the matcher can see.
    """
    return frozenset(_word_codes())


@lru_cache(maxsize=8192)
def _best_match(token: str) -> str | None:
    """Closest vocabulary word to `token`, or None if the call is too close.

    Cached because clinical vocabulary repeats heavily across a consultation
    and across users, and the scan is the one genuinely O(vocabulary) step in
    extraction.
    """
    scored: list[tuple[float, str]] = []
    for word in _word_codes():
        # Length gate first: it is O(1) and removes most candidates before the
        # O(n*m) sequence comparison runs.
        if abs(len(word) - len(token)) > 2:
            continue
        ratio = SequenceMatcher(None, token, word).ratio()
        if ratio >= SIMILARITY_FLOOR:
            scored.append((ratio, word))

    if not scored:
        return None
    scored.sort(reverse=True)
    best_ratio, best_word = scored[0]

    codes = _word_codes()
    best_codes = codes[best_word]
    for ratio, word in scored[1:]:
        if best_ratio - ratio >= MARGIN:
            break  # sorted, so everything after this is further away too
        if not (codes[word] & best_codes):
            # A near-equal candidate meaning something else entirely. Leaving
            # the typo alone costs a follow-up question; picking wrong costs a
            # wrong assessment.
            return None
    return best_word


def repair(text: str) -> str:
    """Rewrite misspelt words onto the medical vocabulary, in place.

    Punctuation and spacing are preserved deliberately. Clause splitting and
    negation scope both run over this string afterwards and both depend on the
    commas and full stops still being where the user put them -- flattening
    them turns "fever but no cough" into one clause and loses the denial.
    """
    known = vocabulary()

    def fix(match: re.Match[str]) -> str:
        original = match.group(0)
        token = original.lower()
        if (
            len(token) < MIN_TOKEN_LENGTH
            or "'" in token  # a contraction is grammar, never a symptom term
            or token in known
            or token in PROTECTED
        ):
            return original
        return _best_match(token) or original

    return _WORD.sub(fix, text)


def reset_cache() -> None:
    """Drop memoised state. For tests that edit the vocabulary."""
    _word_codes.cache_clear()
    vocabulary.cache_clear()
    _best_match.cache_clear()
