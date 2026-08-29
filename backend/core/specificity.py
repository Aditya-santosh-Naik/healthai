"""Symptom specificity weights. Supports pipeline step 4.

Not every symptom carries the same amount of information. `fever` appears in
most of the fourteen conditions and barely narrows anything; `retro_orbital_pain`
appears in exactly one and is close to decisive. Scoring them identically was
why undifferentiated fever produced a four-way tie.

The weight is inverse document frequency over the condition definitions:

    n      = conditions listing this symptom as a feature
    N      = total conditions
    raw    = ln(N / n)
    weight = clamp(0.5 + raw, 0.5, 2.0)

Nothing here is hand-curated. The weights fall out of the knowledge base, so
adding a condition re-derives them and there is no second table to keep in
sync.

**The clamp is load-bearing.** Uncapped, ln(N/1) = 2.64 for any symptom unique
to one condition, and a single such symptom would outweigh three hallmarks of a
common condition -- trading "never diagnoses the rare thing" for "always
diagnoses the rare thing". The floor matters too: without it a symptom shared by
all fourteen would score 0.5 + ln(1) = 0.5 rather than vanishing entirely, which
is right, because even a non-specific symptom is weak evidence rather than none.
"""
import json
import math
from pathlib import Path

from config import DATA_DIR
from core import knowledge

CACHE_PATH = DATA_DIR / "specificity.json"

MIN_WEIGHT = 0.5
MAX_WEIGHT = 2.0
BASE_WEIGHT = 0.5

# A symptom no condition lists cannot discriminate between conditions, but it
# is still something the patient reported. Neutral, not zero.
DEFAULT_WEIGHT = 1.0


def _clamp(value: float) -> float:
    return max(MIN_WEIGHT, min(MAX_WEIGHT, value))


def compute() -> dict[str, float]:
    """Derive weights from the condition YAMLs. Always fresh, never cached."""
    conditions = knowledge.conditions()
    total = len(conditions)
    if not total:
        return {}

    counts: dict[str, int] = {}
    for condition in conditions.values():
        # Deliberately hallmark | supporting | expected, and NOT contradictory.
        # `contradictory` means the symptom argues against the condition, so
        # counting it would treat "rules many things out" as "tells us little"
        # -- backwards. A symptom that contradicts widely is informative.
        for code in condition.all_symptoms:
            counts[code] = counts.get(code, 0) + 1

    return {
        code: round(_clamp(BASE_WEIGHT + math.log(total / n)), 4)
        for code, n in sorted(counts.items())
    }


def _cache_is_stale() -> bool:
    if not CACHE_PATH.exists():
        return True
    cached_at = CACHE_PATH.stat().st_mtime
    condition_files = (DATA_DIR / "conditions").glob("*.yaml")
    return any(path.stat().st_mtime > cached_at for path in condition_files)


def _load() -> dict[str, float]:
    if _cache_is_stale():
        weights = compute()
        CACHE_PATH.write_text(
            json.dumps(weights, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return weights
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt cache must never take the engine down: it is a derived
        # artefact, so recomputing costs microseconds.
        return compute()


_WEIGHTS: dict[str, float] | None = None


def weights() -> dict[str, float]:
    global _WEIGHTS
    if _WEIGHTS is None:
        _WEIGHTS = _load()
    return _WEIGHTS


def weight_for(code: str) -> float:
    return weights().get(code, DEFAULT_WEIGHT)


def reset_cache() -> None:
    """Drop the in-process cache. For tests that edit the knowledge base."""
    global _WEIGHTS
    _WEIGHTS = None


if __name__ == "__main__":  # pragma: no cover - operator convenience
    computed = compute()
    CACHE_PATH.write_text(
        json.dumps(computed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote {CACHE_PATH} ({len(computed)} symptoms)\n")
    for code, value in sorted(computed.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {value:5.2f}  {code}")
