"""Negation scope detection.

A stated negative is evidence, not absence. "No ear pain" must be stored as
present=False so the evidence engine can use it -- acceptance test 3 depends
on this, and it is the difference between reasoning and keyword matching.

Rules, not LLM: a rules approach is more reliable here and is inspectable.
"""
import re

# Cues that negate what follows them, within the same clause.
FORWARD_CUES = [
    "no history of",
    "not experiencing",
    "not having",
    "do not have",
    "does not have",
    "did not have",
    "dont have",
    "doesnt have",
    "didnt have",
    "have not had",
    "has not had",
    "havent had",
    "hasnt had",
    "never had",
    # Bare "never" is needed too: stopword removal turns "never had trouble
    # swallowing" into "never trouble swallowing".
    "never",
    "negative for",
    "free of",
    "ruled out",
    "denies",
    "denied",
    "without any",
    "without",
    "no sign of",
    "no signs of",
    "not any",
    "there is no",
    "there are no",
    "nothing like",
    "hardly any",
    "no",
    "not",
    "neither",
    "nor",
]

# Postfix negation, where the cue FOLLOWS what it negates. English is almost
# entirely prefix ("no cough"), so the forward-scope model above covers it, but
# Hindi, Kannada and Tamil put the negator last: "khansi nahi" is literally
# "cough not". A forward-only model reads that as a reported cough -- turning a
# denial into a symptom, which is the most dangerous direction to be wrong in.
#
# Scope runs BACKWARDS from the cue to the start of the clause, mirroring the
# forward rule.
BACKWARD_CUES = [
    "nahi hai",
    "nahi",
    "nahin",
    "illa",      # Kannada / Tamil
    "illai",     # Tamil
    "ilve",      # Kannada colloquial
    "iralla",    # Kannada
]


# Phrases that contain a cue but do not actually negate.
PSEUDO_NEGATIONS = [
    "no doubt",
    "not only",
    "cannot rule out",
    "can not rule out",
    "not sure",
    "not certain",
    "no better",
    "no relief",
    "not improving",
    "not getting better",
    "no improvement",
    "not settling",
]

# Clause boundaries. Negation does not leak across these.
CLAUSE_SPLIT = re.compile(
    r"(?:[,;.!?]|\band\b|\bbut\b|\balso\b|\bhowever\b|\bthough\b|\bplus\b|\bwhile\b)"
)

_CUE_PATTERNS = [
    (cue, re.compile(r"\b" + re.escape(cue) + r"\b"))
    for cue in sorted(FORWARD_CUES, key=len, reverse=True)
]

_BACKWARD_PATTERNS = [
    re.compile(r"\b" + re.escape(cue) + r"\b")
    for cue in sorted(BACKWARD_CUES, key=len, reverse=True)
]


def split_clauses(text: str) -> list[tuple[int, str]]:
    """Split into clauses, returning (offset_in_text, clause_text).

    Offsets are kept so a caller can map a match back to the original string.
    """
    clauses: list[tuple[int, str]] = []
    cursor = 0
    for match in CLAUSE_SPLIT.finditer(text):
        chunk = text[cursor : match.start()]
        if chunk.strip():
            clauses.append((cursor, chunk))
        cursor = match.end()
    tail = text[cursor:]
    if tail.strip():
        clauses.append((cursor, tail))
    return clauses


def _mask_pseudo_negations(clause: str) -> str:
    """Blank out phrases that look negating but are not, keeping offsets."""
    masked = clause
    for phrase in PSEUDO_NEGATIONS:
        for m in re.finditer(re.escape(phrase), masked):
            masked = masked[: m.start()] + ("#" * len(phrase)) + masked[m.end() :]
    return masked


def negation_spans(clause: str) -> list[tuple[int, int]]:
    """Character ranges within the clause that a negation cue governs.

    Scope runs from the end of the cue to the end of the clause, which is the
    standard forward-scope model and matches how people actually write.
    """
    masked = _mask_pseudo_negations(clause)
    spans: list[tuple[int, int]] = []
    for _cue, pattern in _CUE_PATTERNS:
        for match in pattern.finditer(masked):
            # Skip a cue that sits inside an already-found (longer) cue.
            if any(start <= match.start() < end for start, end in spans):
                continue
            spans.append((match.end(), len(clause)))

    # Postfix cues negate backwards, to the start of the clause.
    for pattern in _BACKWARD_PATTERNS:
        for match in pattern.finditer(masked):
            spans.append((0, match.start()))

    return spans


def is_negated(clause: str, match_start: int) -> bool:
    """Does a negation cue in this clause govern a match at this offset?"""
    return any(start <= match_start < end for start, end in negation_spans(clause))
