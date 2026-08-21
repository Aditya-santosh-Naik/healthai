"""Pull candidate profile facts out of extracted document text.

Rules and the existing vocabularies, not an LLM. Everything found here is a
CANDIDATE only: it lands in extracted_facts with review_status=pending and
reaches the profile only after the user confirms it (invariant on provenance).
"""
import re
from dataclasses import dataclass

from core import knowledge

# Section headers commonly seen on Indian discharge summaries and prescriptions.
SECTION_HINTS = {
    "condition": [
        "diagnosis", "diagnoses", "impression", "known case of", "k/c/o",
        "past history", "medical history", "comorbid",
    ],
    "allergy": ["allergy", "allergies", "allergic to", "drug allergy"],
    "medication": [
        "medication", "medications", "prescription", "rx", "treatment advised",
        "advice", "tab", "cap", "drugs",
    ],
}

# Conditions worth recognising in a document, beyond the 14 assessable ones.
CHRONIC_CONDITIONS = [
    "hypertension", "high blood pressure", "type 2 diabetes", "type 1 diabetes",
    "diabetes mellitus", "diabetes", "asthma", "copd", "hypothyroidism",
    "hyperthyroidism", "chronic kidney disease", "kidney disease",
    "coronary artery disease", "ischemic heart disease", "heart failure",
    "gerd", "acid reflux", "gastritis", "peptic ulcer", "anaemia", "anemia",
    "dyslipidemia", "high cholesterol", "epilepsy", "migraine", "tuberculosis",
]

_DOSE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|iu)\b", re.IGNORECASE)


@dataclass
class CandidateFact:
    fact_type: str  # condition | allergy | medication
    fact_value: str
    confidence: float
    page_ref: int | None = None
    context: str = ""


def _line_pages(pages: list[str]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for index, page in enumerate(pages, start=1):
        for line in page.splitlines():
            stripped = line.strip()
            if stripped:
                out.append((index, stripped))
    return out


def _find_conditions(lines: list[tuple[int, str]]) -> list[CandidateFact]:
    facts: list[CandidateFact] = []
    seen: set[str] = set()
    for page, line in lines:
        lowered = line.lower()
        in_section = any(h in lowered for h in SECTION_HINTS["condition"])
        for condition in CHRONIC_CONDITIONS:
            if condition not in lowered or condition in seen:
                continue
            seen.add(condition)
            facts.append(
                CandidateFact(
                    fact_type="condition",
                    fact_value=condition.title(),
                    # A hit inside a diagnosis section is worth more than a
                    # bare mention somewhere in the text.
                    confidence=0.85 if in_section else 0.55,
                    page_ref=page,
                    context=line[:160],
                )
            )
    return facts


def _find_allergies(lines: list[tuple[int, str]]) -> list[CandidateFact]:
    facts: list[CandidateFact] = []
    seen: set[str] = set()
    for page, line in lines:
        lowered = line.lower()
        if not any(h in lowered for h in SECTION_HINTS["allergy"]):
            continue
        # Everything after the header word is the candidate allergen.
        tail = re.split(r"allerg(?:y|ies|ic to)\s*[:\-]?", lowered, maxsplit=1)
        value = tail[-1].strip(" .:-") if len(tail) > 1 else ""
        if not value or value in {"nil", "none", "no", "nka", "nkda"}:
            continue
        for token in re.split(r"[,;/]| and ", value):
            candidate = token.strip()
            if len(candidate) < 3 or candidate in seen:
                continue
            seen.add(candidate)
            drug = knowledge.resolve_drug(candidate)
            facts.append(
                CandidateFact(
                    fact_type="allergy",
                    fact_value=candidate.title(),
                    confidence=0.8 if drug else 0.6,
                    page_ref=page,
                    context=line[:160],
                )
            )
    return facts


def _find_medications(lines: list[tuple[int, str]]) -> list[CandidateFact]:
    """Match against the known drug vocabulary rather than guessing."""
    facts: list[CandidateFact] = []
    seen: set[str] = set()
    index = knowledge.brand_to_generic()

    for page, line in lines:
        lowered = line.lower()
        for name in sorted(index, key=len, reverse=True):
            if len(name) < 4:
                continue
            if not re.search(r"\b" + re.escape(name) + r"\b", lowered):
                continue
            generic = index[name]
            if generic in seen:
                continue
            seen.add(generic)

            dose_match = _DOSE.search(line)
            display = name.title()
            if dose_match:
                display = f"{display} {dose_match.group(1)}{dose_match.group(2).lower()}"

            in_section = any(h in lowered for h in SECTION_HINTS["medication"])
            facts.append(
                CandidateFact(
                    fact_type="medication",
                    fact_value=display,
                    confidence=0.9 if (dose_match or in_section) else 0.65,
                    page_ref=page,
                    context=line[:160],
                )
            )
            break  # one medicine per line is the usual prescription layout
    return facts


def parse(pages: list[str]) -> list[CandidateFact]:
    """Extract candidate facts. Nothing here is stored on the profile yet."""
    lines = _line_pages(pages)
    facts = _find_conditions(lines) + _find_allergies(lines) + _find_medications(lines)
    # Most confident first, so the review list reads sensibly.
    facts.sort(key=lambda f: -f.confidence)
    return facts
