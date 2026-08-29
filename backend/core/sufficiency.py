"""Information-sufficiency gate. Pipeline step 5.

The novel bit of the project: the system refuses to assess on thin evidence
and says so, rather than printing a confident-sounding guess.
"""
from dataclasses import dataclass

from core.evidence_engine import (
    AMBIGUOUS_LEAD,
    MOST_CONSISTENT_MIN_LEAD,
    MOST_CONSISTENT_MIN_SCORE,
    POSSIBLE_MIN_SCORE,
    Band,
    CandidateResult,
)

# Below this many positive findings, almost any assessment is a guess.
MIN_POSITIVE_SYMPTOMS = 3

# Ceiling on questions per consultation.
#
# There is no single published "average number of questions" a clinician asks,
# so this is not presented as one. What is well established is the SHAPE of a
# focused acute history -- onset and duration, character, severity, associated
# symptoms, relevant negatives, and red-flag screening. Covering that properly
# takes roughly eight to twelve targeted questions, so the ceiling is ten.
#
# The ceiling is rarely reached, because of DECISIVE_LEAD below: a clinician
# stops asking once the picture is clear, and so does this.
MAX_QUESTIONS = 10

# Stop early when one candidate is this far clear of the runner-up. Continuing
# to interrogate someone after the evidence has settled is not thoroughness,
# it is just friction.
#
# Derived from the band thresholds rather than set independently. It used to be
# a bare 5 paired with POSSIBLE_MIN_SCORE, which meant the gate could stop
# asking while the verdict was still only "possible" -- it gave up on becoming
# confident instead of asking the two more questions that would have got there.
# Rescaling the engine then left this constant behind on the old range and the
# consultation ended after four questions with a merely-possible answer.
# Deriving both from the band definition makes "decisive" mean the same thing
# in the gate as it does in the verdict, permanently.
DECISIVE_MIN_SCORE = MOST_CONSISTENT_MIN_SCORE
DECISIVE_LEAD = MOST_CONSISTENT_MIN_LEAD


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

    # Stop early once the evidence has settled. A clinician does not keep
    # working through a checklist after the picture is clear, and neither
    # should this -- the remaining questions would add nothing.
    lead = top.score - ranked[1].score if len(ranked) > 1 else top.score
    if top.score >= DECISIVE_MIN_SCORE and lead >= DECISIVE_LEAD:
        return Sufficiency(
            sufficient=True,
            reason="evidence_decisive",
            detail=(
                f"{top.display_name} is clearly better supported than anything "
                "else, so no further questions were needed."
            ),
        )

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

    if overall_band != Band.MOST_CONSISTENT:
        # The candidates separate, but not far enough to name one.
        #
        # This used to return sufficient, which ended the consultation on a
        # merely "possible" verdict with most of the question budget unspent.
        # On "I have fever and cough" it stopped after four questions -- three
        # of them red-flag screens -- without ever asking about body aches,
        # fatigue or a runny nose, any one of which separates flu from COVID.
        # Stopping there is the same failure as over-diagnosing, just quieter:
        # it declines to find out something it could have found out.
        #
        # Termination is still guaranteed from two directions: MAX_QUESTIONS
        # above is checked before anything else, and next_question returns None
        # once no unanswered symptom would move the ranking, which the pipeline
        # treats as "assess now".
        return Sufficiency(
            sufficient=False,
            reason="not_yet_decisive",
            detail=(
                "The evidence points somewhere, but not clearly enough to name "
                "a most-consistent candidate yet."
            ),
        )

    return Sufficiency(
        sufficient=True,
        reason="evidence_separates",
        detail="One candidate is clearly better supported than the others.",
    )
