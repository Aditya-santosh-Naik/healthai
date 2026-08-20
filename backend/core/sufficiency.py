"""Information-sufficiency gate. Pipeline step 5.

The novel bit of the project: the system refuses to assess on thin evidence
and says so, rather than printing a confident-sounding guess.
"""
from dataclasses import dataclass

from core.evidence_engine import (
    AMBIGUOUS_LEAD,
    POSSIBLE_MIN_SCORE,
    Band,
    CandidateResult,
)

# Below this many positive findings, almost any assessment is a guess.
MIN_POSITIVE_SYMPTOMS = 3
MAX_QUESTIONS = 5


@dataclass
class Sufficiency:
    sufficient: bool
    reason: str
    detail: str


def assess(
    results: list[CandidateResult],
    overall_band: str,
    positive_symptom_count: int,
    questions_asked: int,
) -> Sufficiency:
    """Decide whether to assess now or ask another question."""
    # Hard stop: never interrogate someone indefinitely.
    if questions_asked >= MAX_QUESTIONS:
        return Sufficiency(
            sufficient=True,
            reason="question_limit_reached",
            detail=(
                "Assessment made with the information available after "
                f"{questions_asked} questions."
            ),
        )

    if positive_symptom_count < MIN_POSITIVE_SYMPTOMS:
        return Sufficiency(
            sufficient=False,
            reason="too_few_symptoms",
            detail="Not enough reported symptoms to separate the possibilities.",
        )

    if not results:
        return Sufficiency(
            sufficient=False,
            reason="no_candidates",
            detail="Nothing in the knowledge base matches what has been described.",
        )

    ranked = sorted(results, key=lambda r: r.score, reverse=True)
    top = ranked[0]

    if top.score < POSSIBLE_MIN_SCORE:
        return Sufficiency(
            sufficient=False,
            reason="weak_evidence",
            detail="No candidate has enough supporting evidence yet.",
        )

    if len(ranked) > 1 and (top.score - ranked[1].score) <= AMBIGUOUS_LEAD:
        return Sufficiency(
            sufficient=False,
            reason="candidates_too_close",
            detail=(
                f"{top.display_name} and {ranked[1].display_name} are currently "
                "too close to separate on the evidence available."
            ),
        )

    if overall_band == Band.INSUFFICIENT:
        return Sufficiency(
            sufficient=False,
            reason="insufficient_band",
            detail="The evidence does not yet support naming a most-consistent candidate.",
        )

    return Sufficiency(
        sufficient=True,
        reason="evidence_separates",
        detail="One candidate is clearly better supported than the others.",
    )
