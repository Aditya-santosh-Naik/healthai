"""Evidence engine. Pipeline step 4.

Scores every candidate condition against structured evidence. Deterministic,
inspectable, and entirely rule-driven -- no LLM, no learned weights.

Invariant 1: the score is internal. It is persisted for audit and testing and
is NEVER shown to a user. What the user sees is the ordinal band plus the
actual supporting and contradicting evidence.

Scoring (spec section 7):
    hallmark present       +3 each
    supporting present     +1 each
    expected absent        -2 each
    contradictory present  -3 each
    context modifier       +/-1
    duration mismatch      -1
"""
from dataclasses import dataclass, field

from core import knowledge, specificity
from core.symptom_extraction import ExtractedSymptom

HALLMARK_WEIGHT = 3
SUPPORTING_WEIGHT = 1
EXPECTED_ABSENT_PENALTY = -2
CONTRADICTORY_PENALTY = -3
CONTEXT_WEIGHT = 1
DURATION_MISMATCH_PENALTY = -1

# Prevalence prior, in the same units as the evidence terms. A cold is not more
# likely than dengue because its symptoms fit better -- it is more likely
# before either is examined, and the old engine had no way to say so.
#
# These are ordinal tiers, not probabilities, and they are deliberately small
# enough that specific evidence overrides them: dengue starts 4 points behind a
# cold and still wins outright on retro-orbital pain plus severe body ache.
# Tiers live in each condition's YAML as `base_rate`, with the reasoning in
# `base_rate_note`. All fourteen are author judgement -- see the README
# limitations section.
BASE_RATE_PRIOR = {
    "very_common": 4.0,
    "common": 2.0,
    "uncommon": 0.0,
    "rare": -3.0,
}

# Band thresholds, recalibrated for the scoring above. The previous values
# (6 / 3 / 3 / 2) assumed a range with no prior in it and no specificity
# multiplier; carrying them over unchanged would have made almost everything
# `most_consistent`, replacing over-diagnosis with over-confidence.
#
# Measured over all 96 eval cases with the new scoring:
#
#   TOP score per case      p25  2.49   p50  6.04   p75 11.30   p85 13.94   p90 15.53
#   LEAD over runner-up     p25  0.49   p50  2.00   p70  4.00   p80  6.00   p85  8.00
#
# POSSIBLE_MIN_SCORE is not read off that table. It is anchored: it must be
# strictly greater than the largest base rate prior (very_common = 4.0), or a
# cold would qualify as "possible" on prevalence alone with no evidence at all.
# 6.0 is the smallest round value that clears it with real evidence to spare,
# and it happens to land on the median top score.
POSSIBLE_MIN_SCORE = 6.0

# p85 of top scores and p80 of leads. Reserves the strongest band for roughly
# the top sixth of cases -- appropriate for a system whose claim is that it
# declines to be certain rather than that it usually is.
MOST_CONSISTENT_MIN_SCORE = 14.0
MOST_CONSISTENT_MIN_LEAD = 6.0

# p70 of leads. Below this the top two candidates are not meaningfully
# separated, so the honest outcome is to say so rather than to rank them.
AMBIGUOUS_LEAD = 4.0


class Band:
    MOST_CONSISTENT = "most_consistent"
    POSSIBLE = "possible"
    LESS_CONSISTENT = "less_consistent"
    INSUFFICIENT = "insufficient_information"


@dataclass
class EvidenceItem:
    """One piece of evidence, in language a patient can read."""

    symptom_code: str
    display: str
    kind: str  # hallmark | supporting | expected_absent | contradictory | context | duration
    # Audit trail. Never rendered -- these exist so a ranking can be explained
    # after the fact, and so a test can assert WHY something ranked where it did.
    weight: float = 1.0
    contribution: float = 0.0


@dataclass
class CandidateResult:
    code: str
    display_name: str
    score: float
    band: str
    hallmark_present: bool
    base_rate: str = "uncommon"
    base_rate_contribution: float = 0.0
    supporting: list[EvidenceItem] = field(default_factory=list)
    missing: list[EvidenceItem] = field(default_factory=list)
    contradictory: list[EvidenceItem] = field(default_factory=list)
    context_factors: list[str] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)


@dataclass
class PatientContext:
    """Non-symptom facts that modify candidate strength."""

    age: int | None = None
    smoker: bool = False
    alcohol: bool = False
    conditions: list[str] = field(default_factory=list)
    on_nsaid: bool = False
    monsoon_season: bool = False

    def has_factor(self, factor: str) -> bool:
        if factor == "smoker":
            return self.smoker
        if factor == "alcohol":
            return self.alcohol
        if factor == "elderly":
            return self.age is not None and self.age >= 65
        if factor == "nsaid_use":
            return self.on_nsaid
        if factor == "monsoon_season":
            return self.monsoon_season
        return False


def _duration_mismatch(condition, duration_hours: float | None) -> bool:
    if duration_hours is None:
        return False
    lo, hi = condition.duration_min_hours, condition.duration_max_hours
    if lo is not None and duration_hours < lo:
        return True
    if hi is not None and duration_hours > hi:
        return True
    return False


def score_candidate(
    condition,
    present: set[str],
    denied: set[str],
    duration_hours: float | None,
    context: PatientContext,
) -> CandidateResult:
    # Every candidate starts at its prevalence prior rather than at zero.
    base_rate_contribution = BASE_RATE_PRIOR.get(condition.base_rate, 0.0)
    score = base_rate_contribution

    supporting: list[EvidenceItem] = []
    missing: list[EvidenceItem] = []
    contradictory: list[EvidenceItem] = []
    context_factors: list[str] = []
    hallmark_present = False

    def item(code: str, kind: str, raw: float) -> EvidenceItem:
        """Scale one piece of evidence by how much that symptom discriminates.

        A hallmark that half the knowledge base also claims is worth less than
        a hallmark unique to this condition, in both directions: the same
        scaling applies to penalties, so failing to report a highly specific
        expected symptom counts against the condition more than failing to
        report a generic one.
        """
        nonlocal score
        weight = specificity.weight_for(code)
        contribution = raw * weight
        score += contribution
        return EvidenceItem(
            code, knowledge.display_name(code), kind, weight, contribution
        )

    for code in condition.hallmark:
        if code in present:
            hallmark_present = True
            supporting.append(item(code, "hallmark", HALLMARK_WEIGHT))
        elif code in denied:
            # An explicitly denied hallmark is real evidence against.
            missing.append(item(code, "expected_absent", EXPECTED_ABSENT_PENALTY))

    for code in condition.supporting:
        if code in present:
            supporting.append(item(code, "supporting", SUPPORTING_WEIGHT))

    already_missing = {entry.symptom_code for entry in missing}
    for code in condition.expected:
        if code not in present:
            entry = item(code, "expected_absent", EXPECTED_ABSENT_PENALTY)
            # A denied hallmark that is also an expected symptom already
            # appears above; listing it twice reads as "Runny nose, Runny nose".
            if code not in already_missing:
                missing.append(entry)

    for code in condition.contradictory:
        if code in present:
            contradictory.append(item(code, "contradictory", CONTRADICTORY_PENALTY))

    for modifier in condition.context_modifiers:
        factor = modifier.get("factor", "")
        if not context.has_factor(factor):
            continue
        effect = modifier.get("effect", "strengthen")
        score += CONTEXT_WEIGHT if effect == "strengthen" else -CONTEXT_WEIGHT
        context_factors.append(factor.replace("_", " "))

    if _duration_mismatch(condition, duration_hours):
        score += DURATION_MISMATCH_PENALTY
        missing.append(
            EvidenceItem("duration", "How long this has lasted does not fit the usual pattern", "duration")
        )

    return CandidateResult(
        code=condition.code,
        display_name=condition.display_name,
        score=score,
        band=Band.LESS_CONSISTENT,
        hallmark_present=hallmark_present,
        base_rate=condition.base_rate,
        base_rate_contribution=base_rate_contribution,
        supporting=supporting,
        missing=missing,
        contradictory=contradictory,
        context_factors=context_factors,
        sources=[dict(s) for s in condition.sources],
    )


def assign_bands(results: list[CandidateResult]) -> str:
    """Set each candidate's band and return the overall outcome band.

    Bands are ordinal by design. There is no percentage anywhere in here.
    """
    if not results:
        return Band.INSUFFICIENT

    ranked = sorted(results, key=lambda r: r.score, reverse=True)
    top = ranked[0]
    runner_up_score = ranked[1].score if len(ranked) > 1 else float("-inf")
    lead = top.score - runner_up_score if len(ranked) > 1 else top.score

    for result in ranked:
        if result.score >= POSSIBLE_MIN_SCORE:
            result.band = Band.POSSIBLE
        else:
            result.band = Band.LESS_CONSISTENT

    # Nothing clears the bar, or the top two are too close to separate.
    if top.score < POSSIBLE_MIN_SCORE:
        return Band.INSUFFICIENT
    if len(ranked) > 1 and lead <= AMBIGUOUS_LEAD:
        return Band.INSUFFICIENT

    if top.score >= MOST_CONSISTENT_MIN_SCORE and lead >= MOST_CONSISTENT_MIN_LEAD:
        top.band = Band.MOST_CONSISTENT
        return Band.MOST_CONSISTENT

    return Band.POSSIBLE


def evaluate(
    symptoms: list[ExtractedSymptom],
    context: PatientContext | None = None,
) -> tuple[list[CandidateResult], str]:
    """Score all 14 candidates. Returns (ranked results, overall band)."""
    context = context or PatientContext()
    present = {s.code for s in symptoms if s.present is True}
    denied = {s.code for s in symptoms if s.present is False}
    durations = [
        s.duration_hours for s in symptoms if s.present is True and s.duration_hours
    ]
    duration_hours = max(durations) if durations else None

    results = [
        score_candidate(condition, present, denied, duration_hours, context)
        for condition in knowledge.conditions().values()
    ]
    overall = assign_bands(results)
    results.sort(key=lambda r: r.score, reverse=True)
    return results, overall


def ruled_out(results: list[CandidateResult], limit: int = 3) -> list[CandidateResult]:
    """Candidates the engine considered and set aside, with a visible reason.

    Without this the user cannot tell whether an obvious possibility was even
    looked at. "Why not a common cold?" should be answerable from the page:
    because the patient denied a runny nose, which a cold expects.
    """
    dismissed = [
        r
        for r in results
        if r.score < POSSIBLE_MIN_SCORE and (r.contradictory or r.missing)
    ]
    # Highest score first: the NEAR-MISSES are what a patient wonders about.
    # Ranking by amount of evidence against instead surfaces conditions that
    # were never plausible (GERD for a cough), which explains nothing.
    dismissed.sort(key=lambda r: -r.score)
    return dismissed[:limit]


def top_candidates(results: list[CandidateResult], limit: int = 3) -> list[CandidateResult]:
    """Candidates worth showing. Max 3 (spec section 15).

    Anything scoring below the 'possible' threshold is not surfaced as a
    candidate at all -- listing 14 conditions with faint evidence would be
    noise dressed up as thoroughness.
    """
    return [r for r in results if r.score >= POSSIBLE_MIN_SCORE][:limit]
