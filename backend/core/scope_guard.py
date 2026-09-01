"""Scope guard. Pipeline step 0, runs before everything else.

Invariant 9: under-18, pregnancy and mental-health crisis are refused
outright. A clear, kind refusal with a referral is the correct output. This is
a feature, not a gap -- it shows the limits were understood.
"""
import re
from dataclasses import dataclass

# India-specific crisis resources. Offline project, so these are static.
CRISIS_HELPLINES = [
    "Tele-MANAS (Government of India): 14416 or 1800-891-4416, free, 24x7",
    "KIRAN Mental Health Helpline: 1800-599-0019, free, 24x7",
    "AASRA: +91-9820466726, 24x7",
]


@dataclass
class ScopeRefusal:
    category: str
    message: str
    referral: str
    resources: list[str]


def _any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


# Self-harm and suicidality. Checked first: it outranks everything.
MENTAL_HEALTH_CRISIS = [
    r"\bkill myself\b", r"\bkilling myself\b", r"\bsuicid", r"\bend my life\b",
    r"\bend it all\b", r"\btake my own life\b", r"\bdont want to live\b",
    r"\bdo not want to live\b", r"\bno reason to live\b", r"\bbetter off dead\b",
    r"\bwant to die\b", r"\bharm myself\b", r"\bhurt myself\b",
    r"\bself harm\b", r"\bcutting myself\b", r"\boverdose on purpose\b",
]

MENTAL_HEALTH_GENERAL = [
    r"\bdepress", r"\banxiety attack\b", r"\bpanic attack\b", r"\bmental health\b",
    r"\bbipolar\b", r"\bschizophren", r"\bpsychiatric\b", r"\bpsychosis\b",
    r"\bhearing voices\b", r"\beating disorder\b", r"\banorexi", r"\bbulimi",
]

PREGNANCY = [
    r"\bpregnan", r"\bexpecting a baby\b", r"\bmy baby is due\b",
    r"\b\d{1,2} weeks pregnant\b", r"\btrimester\b", r"\bmissed period and\b",
    r"\bbreastfeed", r"\blactating\b", r"\bpostpartum\b", r"\bpost partum\b",
    r"\bantenatal\b", r"\bmorning sickness\b",
]

# Someone consulting on behalf of a child.
PAEDIATRIC = [
    r"\bmy (?:son|daughter|child|kid|baby|toddler|infant)\b",
    r"\bmy \d{1,2}[- ]year[- ]old\b",
    r"\b\d{1,2} month old\b",
    r"\bmy newborn\b",
    r"\bfor a child\b",
    r"\bpaediatric\b", r"\bpediatric\b",
]

MIN_ADULT_AGE = 18

# Ages the user states about THEMSELVES, in text.
#
# Every PAEDIATRIC pattern above is third-person -- "my son", "my 12-year-old".
# A teenager describing their own symptoms matched none of them and was
# assessed as whatever the profile said, which is the realistic failure: a
# child using a parent's phone, on a profile that says 48. The profile age is
# the primary guard and it is unchanged; this is the case it cannot see.
#
# Matched numerically rather than by pattern alone, so "i am 45" is not caught
# and "I have had this cough for 14 years" -- a duration, not an age -- does
# not read as a child.
_SELF_AGE = [
    re.compile(r"\bi\s*(?:'?m|\s+am)\s+(?:only\s+)?(\d{1,2})\b(?!\s*(?:day|week|month|year)s?\b)"),
    re.compile(r"\bi\s*(?:'?m|\s+am)\s+(?:only\s+)?(\d{1,2})\s*(?:years?|yrs?)\s*old\b"),
    re.compile(r"\b(?:age|aged)\s*(?:is\s*)?(\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})\s*(?:years?|yrs?)[\s-]*old\s+(?:boy|girl|male|female|kid|child|student)\b"),
]


def stated_age(text: str) -> int | None:
    """The youngest age the user states about themselves, if any.

    Youngest rather than first: if a message contains several numbers, the
    safest reading is the one that would refuse.
    """
    found: list[int] = []
    for pattern in _SELF_AGE:
        found.extend(int(m.group(1)) for m in pattern.finditer(text))
    plausible = [a for a in found if 0 < a <= 120]
    return min(plausible) if plausible else None


def check(text: str, patient_age: int | None = None) -> ScopeRefusal | None:
    """Return a refusal if the request is out of scope, else None."""
    lowered = text.lower()

    if _any(lowered, MENTAL_HEALTH_CRISIS):
        return ScopeRefusal(
            category="mental_health_crisis",
            message=(
                "It sounds like you may be going through something extremely "
                "painful right now, and that matters more than anything else "
                "this app could tell you. I am not able to help with this, but "
                "people who can are available right now, free, and will listen."
            ),
            referral=(
                "Please contact one of these helplines now, or go to the nearest "
                "hospital emergency department. If you are in immediate danger, "
                "call 112."
            ),
            resources=CRISIS_HELPLINES,
        )

    if _any(lowered, MENTAL_HEALTH_GENERAL):
        return ScopeRefusal(
            category="mental_health",
            message=(
                "Mental health is outside what this assistant is built to assess. "
                "That is a limitation of this tool, not a comment on how much it "
                "matters."
            ),
            referral=(
                "Please speak to a doctor or a qualified mental health "
                "professional. These helplines are free and available 24x7."
            ),
            resources=CRISIS_HELPLINES,
        )

    if _any(lowered, PREGNANCY):
        return ScopeRefusal(
            category="pregnancy",
            message=(
                "This assistant does not assess symptoms during pregnancy or "
                "breastfeeding. Medication safety and normal symptoms both change "
                "considerably then, and getting it wrong carries real risk."
            ),
            referral=(
                "Please contact your obstetrician, gynaecologist, or midwife. For "
                "anything urgent, go to the nearest maternity unit."
            ),
            resources=[],
        )

    # A stated age overrides the profile, and only ever downwards. Someone
    # typing "I am 14" on a profile that says 48 is the case the profile
    # cannot see -- a child on a parent's account -- and believing the profile
    # there would assess a minor. The reverse is not honoured: an adult age in
    # the text does not unlock a profile that says 12.
    spoken = stated_age(text)
    effective_age = min(
        [a for a in (patient_age, spoken) if a is not None], default=None
    )

    if effective_age is not None and effective_age < MIN_ADULT_AGE:
        return ScopeRefusal(
            category="under_18",
            message=(
                "This assistant is built for adults only. Assessing symptoms in "
                "children is a genuinely different clinical problem -- warning "
                "signs, normal vital signs and safe medicines all differ by age."
            ),
            referral="Please see a paediatrician or your family doctor.",
            resources=[],
        )

    if _any(lowered, PAEDIATRIC):
        return ScopeRefusal(
            category="paediatric",
            message=(
                "It sounds like you are asking about a child. This assistant is "
                "built for adults only, and assessing children needs different "
                "rules for warning signs, normal vital signs and safe medicines."
            ),
            referral="Please see a paediatrician or your family doctor.",
            resources=[],
        )

    return None
