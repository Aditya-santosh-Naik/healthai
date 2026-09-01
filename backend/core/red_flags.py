"""Red-flag detection. Pipeline step 1, runs BEFORE symptom reasoning.

Invariant 2: if a red flag fires, the pipeline halts. No candidate conditions,
no medication advice, no diet advice. A function that reasons first and checks
safety second can talk itself out of escalating; this one returns before any
candidate exists.

Deliberately over-sensitive.
"""
from dataclasses import dataclass

from core import knowledge
from core.symptom_extraction import ExtractedSymptom


@dataclass
class Escalation:
    code: str
    urgency: str          # emergency | urgent
    message: str
    action: str
    source_name: str
    source_url: str
    triggered_by: list[str]

    @property
    def is_emergency(self) -> bool:
        return self.urgency == "emergency"


def check(symptoms: list[ExtractedSymptom]) -> Escalation | None:
    """Return the highest-priority escalation, or None.

    Only positively-reported symptoms can trigger a flag. A denied symptom is
    evidence of absence and must never escalate.

    Implication closure is applied HERE rather than relied on from the caller.
    The meningitis rule is `all_of: [fever, stiff_neck]`, so a patient reporting
    "high fever and a stiff neck" only matches once `high_fever` has been
    expanded to also assert `fever`. Extraction does that today, which meant
    the rule worked through the pipeline and silently failed for any other
    caller -- a test, the PDF path, or whatever gets added next. A safety check
    that depends on the caller having preprocessed correctly is a safety check
    waiting to be bypassed, so it now closes over its own input. Idempotent:
    running it on already-expanded symptoms changes nothing.
    """
    present = {s.code for s in symptoms if s.present is True}
    if not present:
        return None
    present |= knowledge.expand_implied(present)

    for flag in knowledge.red_flags():
        triggered: list[str] = []

        if flag.all_of:
            if not set(flag.all_of) <= present:
                continue
            triggered = list(flag.all_of)
        elif flag.any_of:
            hits = [c for c in flag.any_of if c in present]
            if not hits:
                continue
            triggered = hits
        else:
            continue

        return Escalation(
            code=flag.code,
            urgency=flag.urgency,
            message=flag.message,
            action=flag.action,
            source_name=flag.source_name,
            source_url=flag.source_url,
            triggered_by=[knowledge.display_name(c) for c in triggered],
        )

    return None
