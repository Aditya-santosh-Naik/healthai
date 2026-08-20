"""Deterministic template narration.

Invariant 10: Ollama going down must not break the demo. These templates
produce the full structured result in plainer language, with no model involved.
This path is exercised by the test suite, not just left to rot.
"""
from typing import Any

BAND_PHRASE = {
    "most_consistent": "Your symptoms are most consistent with {name}.",
    "possible": "{name} is possible, but the evidence does not establish it.",
    "less_consistent": "{name} is less consistent with what you have described.",
    "insufficient_information": (
        "There is not enough information to say what this is."
    ),
}


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def narrate_assessment(assessment: dict[str, Any]) -> str:
    """Plain-language summary built entirely from the structured assessment."""
    band = assessment.get("band", "insufficient_information")
    candidates = assessment.get("candidates") or []
    paragraphs: list[str] = []

    # 1. What the evidence points to.
    if band == "insufficient_information" or not candidates:
        opening = (
            "Based on what you have told me so far, there is not enough "
            "information to point to one explanation."
        )
        present = assessment.get("symptoms_present") or []
        if present:
            opening += f" You have reported {_join(present)}."
        opening += (
            " Several conditions can look like this, and separating them needs "
            "more than this assistant can work out from the information given."
        )
        paragraphs.append(opening)
    else:
        top = candidates[0]
        sentence = BAND_PHRASE.get(top["band"], BAND_PHRASE["possible"]).format(
            name=top["display_name"]
        )
        if top.get("supporting"):
            sentence += f" That is based on {_join(top['supporting'])}."
        if top.get("missing"):
            sentence += (
                f" Note that {_join(top['missing'])} would usually be present "
                "and you have not reported it."
            )
        paragraphs.append(sentence)

    # 2. What was considered and looked less likely.
    others = candidates[1:3]
    if others:
        parts: list[str] = []
        for c in others:
            fragment = c["display_name"]
            if c.get("contradictory"):
                fragment += f" (argued against by {_join(c['contradictory'])})"
            elif c.get("missing"):
                fragment += f" (would usually involve {_join(c['missing'])})"
            parts.append(fragment)
        paragraphs.append(
            "Also considered and currently less well supported: " + _join(parts) + "."
        )

    # 3. What to do next.
    steps = assessment.get("next_steps") or []
    if steps:
        paragraphs.append(" ".join(steps))
    else:
        paragraphs.append(
            "Please discuss these symptoms with a doctor or pharmacist, "
            "especially if they get worse or do not start improving."
        )

    return "\n\n".join(paragraphs)


def narrate_escalation(message: str, action: str, triggered_by: list[str]) -> str:
    """Escalation wording without the model."""
    lead = ""
    if triggered_by:
        lead = f"You have reported {_join(triggered_by)}. "
    return f"{lead}{message.strip()}\n\n{action.strip()}"
