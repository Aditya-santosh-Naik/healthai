"""Every LLM prompt in the project lives here and nowhere else (spec section 5).

The contract (spec section 12): the model is rephrasing a COMPLETED assessment.
It never selects a condition, never invents a fact, and never sees raw user
text for reasoning purposes.
"""
import json
from typing import Any

SYSTEM_PROMPT = """You are a careful medical communicator working for a health information assistant in India.

A separate rule-based system has ALREADY completed the clinical assessment. Your only job is to rewrite the structured assessment you are given into clear, plain language for the patient. You are not diagnosing and you are not deciding anything.

HARD RULES. Breaking any of these is a serious error:
1. Use ONLY facts present in the structured assessment and the reference passages provided. Add nothing.
2. Never state or imply a probability. Never use percentages, odds, or phrases like "most likely" or "probably". Use only the wording of the evidence band you are given.
3. Never name a condition that is not in the assessment.
4. Never recommend, suggest, or name a medicine for the patient to take, and never give a dose for anything.
5. Never tell the patient to stop or change any medicine. Only ever say to discuss it with their doctor or pharmacist.
6. Never reassure. Do not say the patient is fine, that it is nothing serious, or that they do not need a doctor.
7. Do not invent symptoms, test results, timelines, or advice.
8. Never use the words "diagnosis", "diagnose", or "diagnosed". You are describing what the evidence is consistent with, not naming a diagnosis.

STYLE:
- Plain English at about an 8th-grade reading level. Short sentences.
- Warm and direct, but not chirpy. No exclamation marks.
- Address the patient as "you".
- Do not use markdown headings, bullets, or bold. Write flowing prose.
- 120 to 200 words total.

Write exactly three short paragraphs of plain prose. Do NOT print any headings, labels, or the descriptions below - they tell you what each paragraph should cover, they are not text to reproduce.

Paragraph 1: what the evidence points to, using the exact band wording given, and the main symptoms supporting it.
Paragraph 2: what else was considered and looked less well supported, and why.
Paragraph 3: what to do next, using only the next steps given to you.

Begin directly with the first paragraph.
"""

ESCALATION_SYSTEM_PROMPT = """You are relaying an urgent medical safety message.

The rule-based system has detected a warning sign and STOPPED. There is no assessment and there are no candidate conditions.

HARD RULES:
1. Output ONLY the escalation message, restated clearly and calmly.
2. Do not name any condition. Do not speculate about the cause.
3. Do not reassure. Do not soften the urgency.
4. Do not mention any medicine.
5. Keep it under 80 words. Plain English, short sentences, no markdown.

Tell the person what was noticed, that it needs to be checked urgently, and exactly what action to take.
"""


def _band_wording(band: str) -> str:
    return {
        "most_consistent": "most consistent with",
        "possible": "possible, but not established",
        "less_consistent": "less consistent with",
        "insufficient_information": "not established - there is not enough information",
    }.get(band, "not established")


def build_assessment_prompt(assessment: dict[str, Any], passages: list[dict[str, str]]) -> str:
    """The single user message for the one assessment call."""
    lines: list[str] = ["STRUCTURED ASSESSMENT (already decided - do not change it):", ""]

    lines.append(f"Overall evidence band: {_band_wording(assessment.get('band', ''))}")
    lines.append("")

    candidates = assessment.get("candidates") or []
    if candidates:
        lines.append("Candidates considered:")
        for c in candidates:
            lines.append(f"- {c['display_name']}: {_band_wording(c['band'])}")
            if c.get("supporting"):
                lines.append(f"    supported by: {', '.join(c['supporting'])}")
            if c.get("contradictory"):
                lines.append(f"    argues against: {', '.join(c['contradictory'])}")
            if c.get("missing"):
                lines.append(f"    expected but not reported: {', '.join(c['missing'])}")
    else:
        lines.append("No candidate reached the evidence threshold.")
    lines.append("")

    if assessment.get("symptoms_present"):
        lines.append(f"Symptoms reported: {', '.join(assessment['symptoms_present'])}")
    if assessment.get("symptoms_denied"):
        lines.append(f"Symptoms explicitly denied: {', '.join(assessment['symptoms_denied'])}")
    if assessment.get("duration_text"):
        lines.append(f"Duration: {assessment['duration_text']}")
    lines.append("")

    if assessment.get("next_steps"):
        lines.append("Next steps to convey (use only these):")
        for step in assessment["next_steps"]:
            lines.append(f"- {step}")
        lines.append("")

    if passages:
        lines.append("REFERENCE PASSAGES (the only outside facts you may use):")
        for p in passages:
            lines.append(f"[{p['source_name']}] {p['text']}")
        lines.append("")
    else:
        lines.append(
            "No reference passages were retrieved. Do not add any information "
            "beyond the structured assessment above."
        )
        lines.append("")

    lines.append(
        "Now write the three paragraphs. Plain prose only, no headings or labels."
    )
    return "\n".join(lines)


def build_escalation_prompt(message: str, action: str, triggered_by: list[str]) -> str:
    return (
        f"Warning sign detected: {', '.join(triggered_by)}\n\n"
        f"Message to convey: {message}\n\n"
        f"Action the person must take: {action}\n\n"
        "Restate this urgently and clearly."
    )


def debug_dump(assessment: dict[str, Any]) -> str:
    """Readable copy of what was sent, for the audit log."""
    return json.dumps(assessment, indent=2, default=str)
