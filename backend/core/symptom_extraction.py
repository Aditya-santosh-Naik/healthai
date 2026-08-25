"""Symptom extraction from free text.

Rules and a controlled vocabulary, not an LLM. The pipeline is:
    normalise -> split into clauses -> longest-alias match -> negation scope
    -> duration and severity parsing

The LLM never sees raw user text for reasoning purposes (invariant 3).
"""
import re
from dataclasses import dataclass

from core import knowledge
from core.negation import is_negated, split_clauses
from core.text_norm import alias_pattern, canonicalise, expand_contractions

# --- normalisation ----------------------------------------------------------


def normalise(text: str) -> str:
    """Light normalisation: lowercase, expand contractions, drop noise.

    Keeps clause punctuation and every word, so duration phrases like "a week"
    survive. Used for duration and severity parsing.
    """
    lowered = expand_contractions(text.lower().strip())
    lowered = re.sub(r"[^\w\s,;.!?-]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def normalise_for_matching(text: str) -> str:
    """Normalisation plus stopword removal, for alias matching.

    Applied once before clause splitting so negation offsets and match offsets
    refer to the same string.
    """
    lowered = normalise(text)
    # Canonicalise per clause-chunk so punctuation separators are preserved.
    parts = re.split(r"([,;.!?])", lowered)
    return "".join(
        part if part in ",;.!?" else " " + canonicalise(part) + " " for part in parts
    )


# --- duration ---------------------------------------------------------------

DURATION_UNITS = {
    "hour": 1.0,
    "hours": 1.0,
    "hr": 1.0,
    "hrs": 1.0,
    "day": 24.0,
    "days": 24.0,
    "week": 168.0,
    "weeks": 168.0,
    "month": 720.0,
    "months": 720.0,
    "year": 8760.0,
    "years": 8760.0,
}

WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "couple": 2,
    "few": 3, "several": 4, "half": 0.5,
}

# "3-4 days", "2 to 3 weeks", "a few days", "10 days", "couple of days"
_RANGE = re.compile(
    r"(\d+)\s*(?:-|to)\s*(\d+)\s*(" + "|".join(DURATION_UNITS) + r")\b"
)
_NUMERIC = re.compile(r"(\d+(?:\.\d+)?)\s*(" + "|".join(DURATION_UNITS) + r")\b")
_WORDY = re.compile(
    r"\b(" + "|".join(WORD_NUMBERS) + r")\s+(?:of\s+)?(" + "|".join(DURATION_UNITS) + r")\b"
)

RELATIVE_DURATIONS = {
    "since yesterday": 24.0,
    "from yesterday": 24.0,
    "yesterday": 24.0,
    "since this morning": 8.0,
    "this morning": 8.0,
    "since morning": 8.0,
    "since last night": 12.0,
    "last night": 12.0,
    "overnight": 12.0,
    "since day before yesterday": 48.0,
    "day before yesterday": 48.0,
    "since last week": 168.0,
    "last week": 168.0,
    "for a while": 336.0,
    "for ages": 720.0,
    "just started": 2.0,
    "just now": 1.0,
    "since today": 8.0,
    "today": 8.0,
}


def parse_duration_hours(text: str) -> float | None:
    """Longest duration mentioned, in hours.

    An explicitly stated duration always beats a vague relative phrase, so
    "this just started an hour back" is 1 hour, not 2.
    """
    normalised = normalise(text)
    explicit: list[float] = []

    # Ranges first, then blank them out so "3-4 days" is not also read as
    # a bare "4 days".
    remaining = normalised
    for match in _RANGE.finditer(normalised):
        lo, hi, unit = match.groups()
        explicit.append((float(lo) + float(hi)) / 2 * DURATION_UNITS[unit])
        remaining = remaining.replace(match.group(0), " ")

    for value, unit in _NUMERIC.findall(remaining):
        explicit.append(float(value) * DURATION_UNITS[unit])

    for word, unit in _WORDY.findall(remaining):
        explicit.append(WORD_NUMBERS[word] * DURATION_UNITS[unit])

    if explicit:
        return max(explicit)

    relative = [h for phrase, h in RELATIVE_DURATIONS.items() if phrase in normalised]
    return max(relative) if relative else None


# --- severity ---------------------------------------------------------------

SEVERITY_WORDS = {
    "slight": 1, "slightly": 1, "mild": 1, "little": 1, "minor": 1,
    "moderate": 2, "medium": 2, "okay": 2,
    "bad": 3, "severe": 3, "severely": 3, "very": 3, "really": 3,
    "high": 3, "strong": 3, "intense": 3, "terrible": 3, "awful": 3,
    "unbearable": 4, "excruciating": 4, "worst": 4, "extreme": 4,
    "extremely": 4, "unbelievable": 4, "cannot bear": 4,
}


def parse_severity(text: str) -> int | None:
    lowered = text.lower()
    found = [score for word, score in SEVERITY_WORDS.items()
             if re.search(r"\b" + re.escape(word) + r"\b", lowered)]
    return max(found) if found else None


# --- extraction -------------------------------------------------------------

@dataclass
class ExtractedSymptom:
    code: str
    # True = reported, False = explicitly denied, None = asked but unknown.
    # None must never be read as a denial.
    present: bool | None
    duration_hours: float | None = None
    severity: int | None = None
    matched_text: str = ""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        sign = "+" if self.present else ("?" if self.present is None else "-")
        return f"<{sign}{self.code} '{self.matched_text}'>"


def _match_clause(clause: str) -> list[tuple[int, int, str, str]]:
    """Non-overlapping alias matches: (start, end, code, matched_text).

    Longest alias wins, so 'dry cough' is matched before 'cough' and the
    'cough' inside it is never matched separately.
    """
    taken: list[tuple[int, int]] = []
    results: list[tuple[int, int, str, str]] = []

    for alias, code in knowledge.alias_index():
        for match in alias_pattern(alias).finditer(clause):
            start, end = match.span()
            if any(start < t_end and t_start < end for t_start, t_end in taken):
                continue
            taken.append((start, end))
            results.append((start, end, code, match.group(0)))

    results.sort(key=lambda r: r[0])
    return results


def extract(text: str) -> list[ExtractedSymptom]:
    """Extract symptoms with presence, duration and severity.

    Later mentions do not overwrite earlier ones; a stated negative is kept
    rather than being dropped.
    """
    normalised = normalise_for_matching(text)
    overall_duration = parse_duration_hours(text)
    found: dict[str, ExtractedSymptom] = {}

    for _offset, clause in split_clauses(normalised):
        clause_duration = parse_duration_hours(clause) or overall_duration
        for start, _end, code, matched in _match_clause(clause):
            negated = is_negated(clause, start)
            existing = found.get(code)
            if existing is not None:
                # A negative mention anywhere wins: safer to treat a symptom as
                # explicitly denied than to assert it on a partial match.
                # `is False` matters -- an unknown must not act like a denial.
                if not negated and existing.present is False:
                    continue
                if negated and existing.present is not False:
                    existing.present = False
                continue

            found[code] = ExtractedSymptom(
                code=code,
                present=not negated,
                duration_hours=None if negated else clause_duration,
                severity=None if negated else parse_severity(clause),
                matched_text=matched,
            )

    # A specific finding entails its broader parent: "high fever" is a fever.
    # Implications never apply to denials.
    positive = {code for code, s in found.items() if s.present is True}
    for implied in knowledge.expand_implied(positive) - set(found):
        parent_of = next(
            (s for s in found.values()
             if s.present is True and implied in knowledge.implications().get(s.code, ())),
            None,
        )
        found[implied] = ExtractedSymptom(
            code=implied,
            present=True,
            duration_hours=parent_of.duration_hours if parent_of else None,
            severity=parent_of.severity if parent_of else None,
            matched_text=f"implied by {parent_of.code}" if parent_of else "implied",
        )

    return list(found.values())


def summarise(symptoms: list[ExtractedSymptom]) -> dict[str, list[str]]:
    """Human-readable split, used in the 'what to tell your doctor' block."""
    return {
        "present": [knowledge.display_name(s.code) for s in symptoms if s.present is True],
        "denied": [knowledge.display_name(s.code) for s in symptoms if s.present is False],
    }
