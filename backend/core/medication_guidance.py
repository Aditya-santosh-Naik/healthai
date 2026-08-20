"""Medication guidance for the result page.

This is NOT a prescribing engine. It never recommends a medicine for this
patient and never gives a dose (invariant 7), and never tells anyone to stop a
prescribed medicine (invariant 8).

Three tiers, all source-cited:

  1. avoid          specific to this patient, naming their actual medicines,
                    allergies and conditions
  2. general_info   the small OTC allowlist the spec permits, mentioned as
                    general information with a see-a-professional caveat
  3. treatment      whether this condition normally needs a doctor-prescribed
                    course, or usually settles on its own

Tier 3 is health information, not a prescription: it says a class of treatment
is typically required and routes the decision to a clinician.
"""
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from config import DATA_DIR
from core import knowledge
from core.medication_safety import SafetyReport, Severity


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    with (DATA_DIR / "treatment_expectations.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@dataclass
class AvoidItem:
    text: str
    source_url: str


@dataclass
class GeneralInfoItem:
    display: str
    used_for: str
    caveat: str
    source_url: str


@dataclass
class TreatmentNote:
    condition_display: str
    needs_prescription: bool
    self_limiting: bool
    summary: str
    source_url: str


@dataclass
class MedicationGuidance:
    avoid: list[AvoidItem] = field(default_factory=list)
    general_info: list[GeneralInfoItem] = field(default_factory=list)
    treatment: list[TreatmentNote] = field(default_factory=list)
    unrecognised: list[str] = field(default_factory=list)

    @property
    def needs_doctor_prescription(self) -> bool:
        return any(t.needs_prescription for t in self.treatment)


def _allergic_to(generic: str, allergies: list[dict[str, str | None]]) -> bool:
    """Would the OTC allowlist item clash with a recorded allergy?"""
    drug = knowledge.drugs().get(generic)
    if drug is None:
        return False
    table = knowledge.cross_reactivity()

    for allergy in allergies:
        allergen = (allergy.get("allergen") or "").strip().lower()
        allergen_class = (allergy.get("allergen_class") or "").strip().lower()

        if allergen and (allergen == generic or allergen in {b.lower() for b in drug.brands}):
            return True
        entry = table.get(allergen_class)
        if entry and drug.drug_class in (
            set(entry.flags_classes) | set(entry.also_caution_classes)
        ):
            return True
    return False


def build(
    condition_codes: list[str],
    safety: SafetyReport,
    allergies: list[dict[str, str | None]] | None = None,
) -> MedicationGuidance:
    """Assemble the three tiers for this patient and these candidates."""
    allergies = allergies or []
    data = _data()
    guidance = MedicationGuidance(unrecognised=list(safety.unrecognised))

    # Tier 1 -- what to avoid, from the patient's own safety findings.
    for finding in safety.findings:
        if finding.severity not in (Severity.AVOID, Severity.CAUTION):
            continue
        guidance.avoid.append(
            AvoidItem(text=finding.reason, source_url=finding.source_url)
        )

    # Tier 3 -- what this condition usually needs. Computed before tier 2 so a
    # prescription-only illness is not muddied by OTC chatter.
    conditions = data.get("conditions", {})
    for code in condition_codes:
        entry = conditions.get(code)
        if entry is None:
            continue
        condition = knowledge.conditions().get(code)
        guidance.treatment.append(
            TreatmentNote(
                condition_display=condition.display_name if condition else code,
                needs_prescription=bool(entry.get("needs_prescription")),
                self_limiting=bool(entry.get("self_limiting")),
                summary=" ".join(str(entry.get("summary", "")).split()),
                source_url=entry.get("source_url", ""),
            )
        )

    # Tier 2 -- OTC general information, filtered against this patient.
    for item in data.get("otc_general_information", []):
        generic = item.get("generic", "")
        if _allergic_to(generic, allergies):
            continue
        # Anything the patient already takes is covered by tier 1 instead.
        if any(
            generic in (m or "").lower() for m in safety.checked_medicines
        ):
            continue
        guidance.general_info.append(
            GeneralInfoItem(
                display=item.get("display", generic),
                used_for=item.get("used_for", ""),
                caveat=" ".join(str(item.get("caveat", "")).split()),
                source_url=item.get("source_url", ""),
            )
        )

    return guidance
