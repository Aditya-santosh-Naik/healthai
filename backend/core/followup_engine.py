"""Follow-up question engine. Pipeline step 6.

Picks the unanswered question whose answer maximally separates the current top
candidates -- a symptom that appears in some candidates' hallmark or supporting
lists and is absent from others'.

Rules (spec section 9):
  - Safety questions first, before any discriminating question.
  - Maximum 5 questions, then force an assessment.
  - One question at a time, with tappable options. Never free text.
  - Never re-ask something already answered.
"""
from dataclasses import dataclass, field

from core import knowledge
from core.evidence_engine import (
    CONTRADICTORY_PENALTY,
    EXPECTED_ABSENT_PENALTY,
    HALLMARK_WEIGHT,
    SUPPORTING_WEIGHT,
    CandidateResult,
)

# How many top candidates the question should try to separate.
DISCRIMINATION_POOL = 4

# The band is decided by the gap between the leader and the runner-up, so
# separating those two is the dominant term. General spread across the
# whole pool is kept only as a tiebreaker.
LEADER_SEPARATION_WEIGHT = 3.0
GENERAL_SPREAD_WEIGHT = 0.3


@dataclass
class Question:
    symptom_code: str
    text: str
    options: list[str] = field(default_factory=lambda: ["Yes", "No", "Not sure"])
    kind: str = "discriminating"  # discriminating | safety
    rationale: str = ""


def _phrase(code: str) -> str:
    """Turn a symptom code into a natural question."""
    display = knowledge.display_name(code).lower()
    special = {
        "productive_cough": "Are you coughing up any phlegm or mucus?",
        "dry_cough": "Is your cough dry, with nothing coming up?",
        "sputum_discoloured": "Is the phlegm yellow or green?",
        "loss_of_smell": "Have you lost your sense of smell?",
        "loss_of_taste": "Have you lost your sense of taste?",
        "retro_orbital_pain": "Do you have pain behind your eyes?",
        "symptoms_worse_lying_down": "Does it get worse when you lie down?",
        "symptoms_worse_after_food": "Does it get worse after eating?",
        "relief_with_antacid": "Does an antacid make it better?",
        "outside_food": "Did you eat anything from outside in the last few days?",
        "sick_contact": "Has anyone around you had the same thing recently?",
        "mosquito_exposure": "Have you been around a lot of mosquitoes lately?",
        "recent_travel": "Have you travelled anywhere recently?",
        "tonsil_exudate": "Are there white patches or spots on your tonsils?",
        "painful_swallowing": "Does it hurt when you swallow?",
        "facial_pressure": "Do you feel pressure or heaviness around your face or forehead?",
        "watery_diarrhoea": "Are the motions very watery?",
        "abdominal_cramps": "Are you getting cramping pains in your stomach?",
        "shortness_of_breath": "Are you finding it hard to breathe?",
        "chest_pain_breathing": "Does your chest hurt when you take a deep breath?",
        "high_fever": "Has your temperature been very high?",
        "chills": "Have you had chills or shivering?",
        "rash": "Have you noticed any rash on your skin?",
        "joint_pain": "Are your joints aching?",
        "severe_body_ache": "Are your body aches severe rather than mild?",
        "heartburn": "Do you get a burning feeling in your chest?",
        "upper_abdominal_pain": "Is the pain in the upper part of your stomach?",
    }
    if code in special:
        return special[code]
    return f"Do you have {display}?"


def _safety_question(code: str) -> str:
    special = {
        "severe_abdominal_pain": "Is your stomach pain severe?",
        "persistent_vomiting": "Are you able to keep any fluids down?",
        "bleeding_gums": "Have you noticed any bleeding from your gums or nose?",
        "black_stools": "Have your stools been black or tarry?",
        "shortness_of_breath": "Are you having any difficulty breathing?",
        "chest_pain": "Do you have any chest pain?",
        "confusion": "Have you felt confused or unusually drowsy?",
        "blood_in_sputum": "Have you coughed up any blood?",
        "low_urine_output": "Are you passing a normal amount of urine?",
        "lethargy_restlessness": "Have you felt extremely tired or restless?",
        "stiff_neck": "Is your neck stiff?",
        "bloody_stools": "Have you seen any blood in your stools?",
    }
    return special.get(code, _phrase(code))


# Questions where "No" is the reassuring answer, so the options read naturally.
_INVERTED_OPTIONS = {
    "persistent_vomiting": ["I can keep fluids down", "I cannot keep anything down", "Not sure"],
    "low_urine_output": ["Normal amount", "Much less than usual", "Not sure"],
}


def _pending_safety_questions(
    present: set[str], answered: set[str], candidates: list[CandidateResult]
) -> list[str]:
    """Red-flag screening symptoms relevant to the candidates on the table.

    Only symptoms on the curated screening list are asked about, in its
    priority order. Extreme signs a patient would already have volunteered
    (blue lips, seizures) are excluded: asking about them burns the
    five-question budget without adding information. They still escalate
    instantly if reported.
    """
    relevant: set[str] = set()
    for candidate in candidates:
        condition = knowledge.conditions().get(candidate.code)
        if condition is None:
            continue
        relevant.update(condition.red_flags)

    return [
        code
        for code in knowledge.screening_questions()
        if code in relevant and code not in present and code not in answered
    ]


def _gain(code: str, condition, answered_yes: bool) -> float:
    """How a candidate's score would move if this symptom were answered.

    The two answers are NOT symmetric, and that asymmetry is the whole point:
    a contradictory symptom only penalises when it is PRESENT, so answering
    "no" to it changes nothing. A hallmark, by contrast, moves the score
    either way -- up if reported, down if explicitly denied.
    """
    if answered_yes:
        if code in condition.hallmark:
            return float(HALLMARK_WEIGHT)
        if code in condition.supporting:
            return float(SUPPORTING_WEIGHT)
        if code in condition.contradictory:
            return float(CONTRADICTORY_PENALTY)
        return 0.0

    # Answered "no". Only a denied hallmark carries evidential weight.
    if code in condition.hallmark:
        return float(EXPECTED_ABSENT_PENALTY)
    return 0.0


def _separation(gains: list[float]) -> float:
    """How far this answer would push the leader away from the runner-up."""
    return abs(gains[0] - gains[1]) if len(gains) > 1 else 0.0


def _spread(gains: list[float]) -> float:
    """General splitting power across the whole pool, as a tiebreaker."""
    movers = sum(1 for g in gains if g != 0)
    if movers == 0 or movers == len(gains):
        return 0.0
    balance = 1.0 - abs((movers / len(gains)) - 0.5) * 2
    return (max(gains) - min(gains)) * (0.5 + balance)


def _discrimination_value(code: str, candidates: list[CandidateResult]) -> float:
    """Expected information from asking about this symptom.

    Scored as the EXPECTED separation across both possible answers, not the
    best case. Scoring only the "yes" branch made the engine ask about
    symptoms that are merely contradictory for the runner-up -- a "no" there
    moves nothing, so half the time the question was wasted and the
    consultation ended on insufficient_information.

    A symptom that is a hallmark for one leader and not the other separates
    them whichever way it is answered, and that is what gets picked now.
    """
    if not candidates:
        return 0.0

    conditions = [knowledge.conditions().get(c.code) for c in candidates]
    if any(c is None for c in conditions):
        return 0.0

    yes = [_gain(code, c, True) for c in conditions]
    no = [_gain(code, c, False) for c in conditions]

    if not any(yes) and not any(no):
        return 0.0

    expected_separation = 0.5 * _separation(yes) + 0.5 * _separation(no)
    expected_spread = 0.5 * _spread(yes) + 0.5 * _spread(no)

    return (
        expected_separation * LEADER_SEPARATION_WEIGHT
        + expected_spread * GENERAL_SPREAD_WEIGHT
    )


def next_question(
    candidates: list[CandidateResult],
    present: set[str],
    denied: set[str],
    questions_asked: int,
    unknown: set[str] | None = None,
) -> Question | None:
    """Pick the next question, or None if there is nothing useful left to ask.

    `unknown` holds symptoms that were ASKED and answered "Not sure". They
    count as answered for selection purposes even though they contribute no
    evidence -- otherwise the same question is selected forever.
    """
    from core.sufficiency import MAX_QUESTIONS

    if questions_asked >= MAX_QUESTIONS:
        return None

    answered = present | denied | (unknown or set())
    pool = candidates[:DISCRIMINATION_POOL]

    # 1. Safety first, but capped. Screening must not crowd out the questions
    #    that actually separate the candidates.
    safety_asked = len(
        [c for c in answered if c in set(knowledge.screening_questions())]
    )
    if safety_asked < knowledge.max_safety_questions():
        for code in _pending_safety_questions(present, answered, pool):
            return Question(
                symptom_code=code,
                text=_safety_question(code),
                options=_INVERTED_OPTIONS.get(code, ["Yes", "No", "Not sure"]),
                kind="safety",
                rationale="Screening for a warning sign before going further.",
            )

    # 2. Then the most discriminating unanswered symptom.
    seen: set[str] = set()
    scored: list[tuple[float, str]] = []
    for candidate in pool:
        condition = knowledge.conditions().get(candidate.code)
        if condition is None:
            continue
        for code in condition.all_symptoms:
            if code in answered or code in seen:
                continue
            seen.add(code)
            value = _discrimination_value(code, pool)
            if value > 0:
                scored.append((value, code))

    if not scored:
        return None

    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    best_value, best_code = scored[0]

    return Question(
        symptom_code=best_code,
        text=_phrase(best_code),
        options=_INVERTED_OPTIONS.get(best_code, ["Yes", "No", "Not sure"]),
        kind="discriminating",
        rationale=(
            "This answer separates "
            + " and ".join(c.display_name for c in pool[:2])
            + " better than anything else left to ask."
            if len(pool) > 1
            else "This narrows down the remaining possibilities."
        ),
    )


def apply_answer(question_code: str, answer: str):
    """Map a tapped option onto a symptom observation.

    "Not sure" records presence as None -- asked, but unknown. An unknown is
    never treated as a denial, which would be a silent fabrication, but it
    must still be remembered or the question repeats forever.
    """
    from core.symptom_extraction import ExtractedSymptom

    normalised = answer.strip().lower()
    positive = {"yes", "y", "i cannot keep anything down", "much less than usual"}
    negative = {"no", "n", "i can keep fluids down", "normal amount"}

    if normalised in positive:
        return ExtractedSymptom(
            code=question_code, present=True, matched_text=f"answered: {answer}"
        )
    if normalised in negative:
        return ExtractedSymptom(
            code=question_code, present=False, matched_text=f"answered: {answer}"
        )
    # "Not sure" or a skip: record that it was ASKED, with presence unknown.
    # Returning nothing here meant the symptom stayed unanswered and the same
    # question was selected again on the next turn.
    return ExtractedSymptom(
        code=question_code, present=None, matched_text=f"answered: {answer}"
    )
