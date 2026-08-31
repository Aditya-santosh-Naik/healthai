"""Clinical eval harness: diagnosis, diet, lifestyle.

Two different kinds of check, because they catch different failures.

**Diagnosis** is scored against labelled cases -- input in, expected leading
condition out. A ranking test needs labels; there is no way around it.

**Diet and lifestyle** are scored by CONTRADICTION instead. Labelling the
expected advice for every condition and profile combination would mean writing
out the templates a second time, and the test would then only prove the two
copies match. What actually goes wrong is advice that is individually
reasonable and collectively unsafe: telling a hypertensive patient to drink
salted lassi is not wrong as cold advice, it is wrong for that patient. So the
harness enumerates every condition x profile combination and asserts that
nothing recommended violates that patient's own constraints.

Run from the backend directory:
    .venv/Scripts/python.exe -m tools.eval_clinical
    .venv/Scripts/python.exe -m tools.eval_clinical --verbose
"""
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR  # noqa: E402
from core import diet_lifestyle, evidence_engine, knowledge  # noqa: E402
from core.symptom_extraction import extract  # noqa: E402

DIAGNOSIS_SET = DATA_DIR / "eval" / "diagnosis_cases.yaml"

# What a given patient must never be told to consume. Substring match against
# the recommendation text, lowercased -- crude, but these are curated templates
# with a small vocabulary, and a false alarm here is cheap to inspect.
FORBIDDEN_FOR = {
    "hypertension": [
        "salted", "pickle", "papad", "namkeen", "soy sauce", "processed",
    ],
    "type 2 diabetes": [
        "sugary", "fruit juice", "honey", "jaggery", "sweet", "glucose",
        "soft drink", "banana shake",
    ],
}
# Chronic kidney disease was in this table and has been removed. The system
# does not model it, no seeded patient has it, and the potassium and protein
# restrictions it implies are a different clinical problem. Testing against a
# condition the system never claims to handle produces failures that cannot be
# acted on.

# Recommendations that LOOK like violations and are not. Each needs a reason,
# because an exception list is otherwise just a way to make a failing test
# pass.
ALLOWED_DESPITE_MATCH = {
    # "Oral rehydration salts" trips the salt check. ORS is the correct
    # treatment for dehydration and withholding it from a hypertensive patient
    # with gastroenteritis is the dangerous option, not the safe one -- the
    # sodium in a sachet taken for a few days is not the sodium load that
    # matters in hypertension.
    "oral rehydration salts",
    # Naming a food in order to warn against it is the advice working.
    "avoid",
    "limit",
    "cut down",
    "stay away from",
    # A qualified broth is not the meat stock the bare word implies.
    "vegetable broth",
}

FORBIDDEN_FOR_DIET = {
    "veg": ["chicken", "mutton", "fish", "egg", "meat", "prawn", "broth"],
    "vegan": [
        "chicken", "mutton", "fish", "egg", "meat", "prawn", "broth",
        "curd", "milk", "ghee", "paneer", "buttermilk", "lassi", "yoghurt",
        "yogurt", "dahi", "butter", "cheese",
    ],
    "jain": [
        "chicken", "mutton", "fish", "egg", "meat", "onion", "garlic",
        "potato", "radish", "carrot",
    ],
    "non_veg": [],
}

# Only these sections actually recommend something. "avoid" naming a food is
# the advice working, not failing.
RECOMMENDING = {
    diet_lifestyle.Category.DIET_PREFER,
    diet_lifestyle.Category.HYDRATION,
}


def check_diet_consistency() -> list[str]:
    """Every condition x diet type x comorbidity. Returns violations."""
    violations: list[str] = []
    conditions = list(knowledge.conditions())

    for code in conditions:
        for diet_type, banned_foods in FORBIDDEN_FOR_DIET.items():
            for comorbidity, banned_med in list(FORBIDDEN_FOR.items()) + [(None, [])]:
                comorbidities = [comorbidity] if comorbidity else []
                plan = diet_lifestyle.build(
                    [code], diet_type=diet_type, conditions=comorbidities
                )
                for rec in plan.recommendations:
                    if rec.category not in RECOMMENDING:
                        continue
                    text = rec.text.lower()
                    if any(ok in text for ok in ALLOWED_DESPITE_MATCH):
                        continue
                    for term in banned_foods:
                        if term in text:
                            violations.append(
                                f"{code} / {diet_type}: recommends {term!r} -- {rec.text}"
                            )
                    for term in banned_med:
                        if term in text:
                            violations.append(
                                f"{code} / {comorbidity}: recommends {term!r} -- {rec.text}"
                            )
    return violations


def check_every_condition_has_guidance() -> list[str]:
    """A condition that can be diagnosed but produces no advice is a hole."""
    gaps: list[str] = []
    for code in knowledge.conditions():
        plan = diet_lifestyle.build([code], diet_type="veg")
        by_cat = {r.category for r in plan.recommendations}
        for required in (
            diet_lifestyle.Category.DIET_PREFER,
            diet_lifestyle.Category.DIET_AVOID,
            diet_lifestyle.Category.WARNING_SIGN,
        ):
            if required not in by_cat:
                gaps.append(f"{code}: no {required} guidance")
    return gaps


def check_diagnosis() -> tuple[int, int, list[str]]:
    """Labelled ranking cases. Returns (passed, total, failures)."""
    if not DIAGNOSIS_SET.exists():
        return 0, 0, [f"missing dataset: {DIAGNOSIS_SET}"]

    cases = yaml.safe_load(DIAGNOSIS_SET.read_text(encoding="utf-8"))["cases"]
    failures: list[str] = []
    passed = 0

    for case in cases:
        results, band = evidence_engine.evaluate(extract(case["text"]))
        expect_band = case.get("band")
        expect_top = case.get("top")

        if expect_band and band != expect_band:
            failures.append(f"{case['text']!r}: band {band}, expected {expect_band}")
            continue
        if expect_top and (not results or results[0].code != expect_top):
            got = results[0].code if results else "nothing"
            failures.append(f"{case['text']!r}: top {got}, expected {expect_top}")
            continue
        passed += 1

    return passed, len(cases), failures


def main(verbose: bool = False) -> int:
    started = time.perf_counter()

    diag_passed, diag_total, diag_failures = check_diagnosis()
    diet_violations = check_diet_consistency()
    coverage_gaps = check_every_condition_has_guidance()

    def pct(hit: int, total: int) -> str:
        return f"{100.0 * hit / total:5.1f}%" if total else "  n/a"

    print("=" * 72)
    print("CLINICAL EVALUATION -- diagnosis, diet, lifestyle")
    print("=" * 72)
    print(f"diagnosis ranking       {diag_passed}/{diag_total}   {pct(diag_passed, diag_total)}")
    print(f"diet contradictions     {len(diet_violations)}   (must be 0)")
    print(f"guidance coverage gaps  {len(coverage_gaps)}   (must be 0)")
    print(f"elapsed                 {time.perf_counter() - started:.2f}s")
    print()

    for title, items in (
        ("DIAGNOSIS FAILURES", diag_failures),
        ("DIET CONTRADICTIONS", sorted(set(diet_violations))),
        ("COVERAGE GAPS", coverage_gaps),
    ):
        if items:
            print(f"--- {len(items)} {title} ---")
            for item in items if verbose else items[:15]:
                print(f"  {item}")
            if not verbose and len(items) > 15:
                print(f"  ... and {len(items) - 15} more (--verbose for all)")
            print()

    ok = not (diag_failures or diet_violations or coverage_gaps)
    if ok:
        print("All clinical checks pass.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(verbose="--verbose" in sys.argv))
