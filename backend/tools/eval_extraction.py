"""Measure the symptom extractor against the labelled natural-language set.

This is the tuning loop for "it needs to understand normal English". There is
no neural model being fitted -- the extractor is deterministic rules -- but the
method is the same: label real phrasings, measure, fix the gaps, re-measure.

Run from the backend directory:
    .venv/Scripts/python.exe -m tools.eval_extraction
    .venv/Scripts/python.exe -m tools.eval_extraction --verbose
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR  # noqa: E402
from core import knowledge  # noqa: E402
from core.symptom_extraction import extract, parse_duration_hours  # noqa: E402

DATASET = DATA_DIR / "eval" / "nl_symptom_cases.yaml"
DURATION_TOLERANCE = 0.01  # duration is computed, so require near-exact


@dataclass
class CaseResult:
    text: str
    missed_present: list[str] = field(default_factory=list)
    missed_absent: list[str] = field(default_factory=list)
    forbidden_hits: list[str] = field(default_factory=list)
    spurious: list[str] = field(default_factory=list)
    duration_expected: float | None = None
    duration_actual: float | None = None

    @property
    def duration_wrong(self) -> bool:
        if self.duration_expected is None:
            return False
        if self.duration_actual is None:
            return True
        return abs(self.duration_actual - self.duration_expected) > DURATION_TOLERANCE

    @property
    def passed(self) -> bool:
        return not (
            self.missed_present
            or self.missed_absent
            or self.forbidden_hits
            or self.duration_wrong
        )


def evaluate_case(case: dict) -> CaseResult:
    text = case["text"]
    expect_present = set(case.get("present") or [])
    expect_absent = set(case.get("absent") or [])
    forbid = set(case.get("forbid") or [])

    extracted = extract(text)
    got_present = {s.code for s in extracted if s.present}
    got_absent = {s.code for s in extracted if not s.present}

    # Implied parents of expected symptoms are legitimate, not spurious.
    allowed = knowledge.expand_implied(expect_present) | expect_present

    result = CaseResult(
        text=text,
        missed_present=sorted(expect_present - got_present),
        missed_absent=sorted(expect_absent - got_absent),
        forbidden_hits=sorted(forbid & (got_present | got_absent)),
        spurious=sorted(got_present - allowed),
        duration_expected=case.get("duration_hours"),
        duration_actual=parse_duration_hours(text),
    )
    return result


def main(verbose: bool = False) -> int:
    with DATASET.open(encoding="utf-8") as fh:
        cases = yaml.safe_load(fh)["cases"]

    results = [evaluate_case(c) for c in cases]

    total = len(results)
    passed = sum(1 for r in results if r.passed)

    required_present = sum(len(c.get("present") or []) for c in cases)
    missed_present = sum(len(r.missed_present) for r in results)
    required_absent = sum(len(c.get("absent") or []) for c in cases)
    missed_absent = sum(len(r.missed_absent) for r in results)
    forbidden = sum(len(r.forbidden_hits) for r in results)
    spurious = sum(len(r.spurious) for r in results)
    duration_cases = sum(1 for r in results if r.duration_expected is not None)
    duration_wrong = sum(1 for r in results if r.duration_wrong)

    def pct(hit: int, total_: int) -> str:
        return f"{100.0 * hit / total_:5.1f}%" if total_ else "  n/a"

    print("=" * 72)
    print("SYMPTOM EXTRACTION -- natural language evaluation")
    print("=" * 72)
    print(f"cases passed fully      {passed}/{total}   {pct(passed, total)}")
    print(
        f"symptom recall          {required_present - missed_present}/{required_present}"
        f"   {pct(required_present - missed_present, required_present)}"
    )
    print(
        f"negation recall         {required_absent - missed_absent}/{required_absent}"
        f"   {pct(required_absent - missed_absent, required_absent)}"
    )
    print(
        f"duration accuracy       {duration_cases - duration_wrong}/{duration_cases}"
        f"   {pct(duration_cases - duration_wrong, duration_cases)}"
    )
    print(f"forbidden false hits    {forbidden}   (must be 0)")
    print(f"spurious extractions    {spurious}   (informational)")
    print()

    failures = [r for r in results if not r.passed]
    if failures:
        print(f"--- {len(failures)} FAILING CASES ---")
        for r in failures:
            print(f'\n  "{r.text}"')
            if r.missed_present:
                print(f"      missed present : {r.missed_present}")
            if r.missed_absent:
                print(f"      missed negation: {r.missed_absent}")
            if r.forbidden_hits:
                print(f"      FORBIDDEN hit  : {r.forbidden_hits}")
            if r.duration_wrong:
                print(
                    f"      duration       : expected {r.duration_expected}, "
                    f"got {r.duration_actual}"
                )
    else:
        print("All cases pass.")

    if verbose:
        noisy = [r for r in results if r.spurious]
        if noisy:
            print(f"\n--- {len(noisy)} cases with spurious extractions ---")
            for r in noisy:
                print(f'  "{r.text[:60]}" -> {r.spurious}')

    return 0 if forbidden == 0 and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main(verbose="--verbose" in sys.argv))
