"""Medication safety. Pipeline step 7.

This is NOT a prescribing engine and never suggests what to take. It comments
only on the safety of medicines the patient already takes (invariant 7), and
never tells anyone to stop a prescribed medicine (invariant 8) -- only to
discuss it with their doctor or pharmacist.

Four checks:
  1. drug x drug        interactions between the patient's own medicines
  2. drug x allergy     cross-reactivity BY CLASS, not by name
  3. drug x condition   contraindications against the patient's conditions
  4. ADR                could a current medicine be causing the symptom?

Check 4 is the most clinically valuable thing in the build.
"""
from dataclasses import dataclass, field

from core import knowledge


class Severity:
    NONE = "none"
    CAUTION = "caution"
    AVOID = "avoid"


_RANK = {Severity.NONE: 0, Severity.CAUTION: 1, Severity.AVOID: 2}


@dataclass
class SafetyFinding:
    subject_drug: str            # what the patient recognises: their brand name
    related: str | None          # the other drug, condition, or allergen
    severity: str
    reason: str
    source_url: str
    kind: str                    # drug_drug | drug_allergy | drug_condition | adverse_reaction


@dataclass
class PatientMedicine:
    """A medicine as the patient knows it, plus what we resolved it to."""

    label: str                   # "Combiflam" -- what to call it back to them
    generic: str | None
    drug_class: str | None
    side_effects: tuple[str, ...] = ()
    recognised: bool = True
    # Combination products expand to their parts: Combiflam is
    # "ibuprofen+paracetamol", but interaction rules are keyed on "ibuprofen".
    components: tuple[str, ...] = ()

    def matches(self, generic: str) -> bool:
        return generic == self.generic or generic in self.components


@dataclass
class SafetyReport:
    findings: list[SafetyFinding] = field(default_factory=list)
    unrecognised: list[str] = field(default_factory=list)
    checked_medicines: list[str] = field(default_factory=list)

    @property
    def overall(self) -> str:
        if not self.findings:
            return Severity.NONE
        return max((f.severity for f in self.findings), key=lambda s: _RANK[s])

    @property
    def has_findings(self) -> bool:
        return bool(self.findings)


def resolve_medicines(entries: list[dict[str, str | None]]) -> list[PatientMedicine]:
    """Resolve brand names to generics.

    Invariant: an unrecognised medicine is reported, never silently skipped.
    """
    resolved: list[PatientMedicine] = []
    for entry in entries:
        brand = entry.get("brand_name")
        generic_hint = entry.get("generic_name")
        label = brand or generic_hint or "Unnamed medicine"

        drug = knowledge.resolve_drug(brand) or knowledge.resolve_drug(generic_hint)
        if drug is None:
            resolved.append(
                PatientMedicine(label=label, generic=None, drug_class=None, recognised=False)
            )
            continue

        resolved.append(
            PatientMedicine(
                label=label,
                generic=drug.generic,
                drug_class=drug.drug_class,
                side_effects=drug.side_effects,
                recognised=True,
                components=tuple(part.strip() for part in drug.generic.split("+")),
            )
        )
    return resolved


def _classes_of(medicine: PatientMedicine) -> set[str]:
    """Every drug class this product belongs to, components included."""
    classes = {medicine.drug_class} if medicine.drug_class else set()
    for component in medicine.components:
        part = knowledge.drugs().get(component)
        if part:
            classes.add(part.drug_class)
    return classes


def _check_drug_drug(medicines: list[PatientMedicine]) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []

    def find(generic: str) -> PatientMedicine | None:
        return next((m for m in medicines if m.matches(generic)), None)

    for rule in knowledge.interactions():
        if rule.type != "drug_drug":
            continue
        subject = find(rule.subject)
        other = find(rule.object)
        if subject is None or other is None or subject is other:
            continue
        findings.append(
            SafetyFinding(
                subject_drug=subject.label,
                related=other.label,
                severity=rule.severity,
                reason=(
                    f"You take both {subject.label} and {other.label}. {rule.reason} "
                    "Do not stop either one on your own -- raise it with your doctor "
                    "or pharmacist."
                ),
                source_url=rule.source_url,
                kind="drug_drug",
            )
        )
    return findings


def _check_drug_allergy(
    medicines: list[PatientMedicine], allergies: list[dict[str, str | None]]
) -> list[SafetyFinding]:
    """Cross-reactivity by class.

    A penicillin allergy must flag amoxicillin even though the two names share
    no substring. This is the check a naive name-match system gets wrong.
    """
    findings: list[SafetyFinding] = []
    table = knowledge.cross_reactivity()

    for allergy in allergies:
        allergen = (allergy.get("allergen") or "").strip()
        allergen_class = (allergy.get("allergen_class") or "").strip().lower()

        # If no class was recorded, try to infer one from the allergen name.
        if not allergen_class or allergen_class == "other":
            drug = knowledge.resolve_drug(allergen)
            allergen_class = drug.drug_class if drug else allergen_class

        entry = table.get(allergen_class)
        if entry is None:
            continue

        for medicine in medicines:
            medicine_classes = _classes_of(medicine)
            if not medicine_classes:
                continue
            if medicine_classes & set(entry.flags_classes):
                findings.append(
                    SafetyFinding(
                        subject_drug=medicine.label,
                        related=allergen,
                        severity=Severity.AVOID,
                        reason=(
                            f"You have recorded an allergy to {allergen}. "
                            f"{medicine.label} belongs to the same group "
                            f"({entry.display}), so it can cause the same reaction "
                            "even though the name is different. Make sure every "
                            "doctor and pharmacist you see knows about this allergy."
                        ),
                        source_url=entry.source_url,
                        kind="drug_allergy",
                    )
                )
            elif medicine_classes & set(entry.also_caution_classes):
                findings.append(
                    SafetyFinding(
                        subject_drug=medicine.label,
                        related=allergen,
                        severity=Severity.CAUTION,
                        reason=(
                            f"You have recorded an allergy to {allergen}. "
                            f"{medicine.label} is in a related group, and a small "
                            "number of people react to both. "
                            f"{entry.note} Mention it to your doctor."
                        ),
                        source_url=entry.source_url,
                        kind="drug_allergy",
                    )
                )
    return findings


# Lifestyle factors arrive through the same channel as conditions, because
# they match the same rules -- but they are not conditions and must not read
# as a diagnosis. "You take Metrogyl and have alcohol use" is both ungrammatical
# and wrong about the patient.
_LIFESTYLE_PHRASING = {
    "alcohol use": "drink alcohol",
    "smoking": "smoke",
}


def _phrase_for(matched: str) -> str:
    return _LIFESTYLE_PHRASING.get(matched.strip().lower(), f"have {matched}")


def _check_drug_condition(
    medicines: list[PatientMedicine], conditions: list[str]
) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    normalised = {c.strip().lower(): c.strip() for c in conditions if c and c.strip()}

    for rule in knowledge.interactions():
        if rule.type != "drug_condition":
            continue
        target = rule.object.strip().lower()

        matched_condition = None
        for key, original in normalised.items():
            if target == key or target in key or key in target:
                matched_condition = original
                break
        if matched_condition is None:
            continue

        for medicine in medicines:
            if not medicine.matches(rule.subject):
                continue
            findings.append(
                SafetyFinding(
                    subject_drug=medicine.label,
                    related=matched_condition,
                    severity=rule.severity,
                    reason=(
                        f"You take {medicine.label} and {_phrase_for(matched_condition)}. "
                        f"{rule.reason} Do not change anything on your own -- "
                        "discuss it with your doctor or pharmacist."
                    ),
                    source_url=rule.source_url,
                    kind="drug_condition",
                )
            )
    return findings


def _check_adverse_reactions(
    medicines: list[PatientMedicine], present_symptoms: set[str]
) -> list[SafetyFinding]:
    """Could a medicine the patient already takes be causing the symptom?

    Commonly missed in practice, and the most useful thing this layer does.
    """
    findings: list[SafetyFinding] = []
    for medicine in medicines:
        effects = set(medicine.side_effects)
        for component in medicine.components:
            part = knowledge.drugs().get(component)
            if part:
                effects |= set(part.side_effects)
        overlap = [c for c in sorted(effects) if c in present_symptoms]
        if not overlap:
            continue
        names = ", ".join(knowledge.display_name(c).lower() for c in overlap)
        drug = knowledge.drugs().get(medicine.generic or "")
        findings.append(
            SafetyFinding(
                subject_drug=medicine.label,
                related=names,
                severity=Severity.CAUTION,
                reason=(
                    f"One of your current medicines, {medicine.label}, can sometimes "
                    f"cause {names}. That does not mean it is the cause here, but it "
                    "is worth mentioning to your doctor. Keep taking it as prescribed "
                    "unless they tell you otherwise."
                ),
                source_url=drug.source_url if drug else "",
                kind="adverse_reaction",
            )
        )
    return findings


def evaluate(
    medications: list[dict[str, str | None]],
    allergies: list[dict[str, str | None]],
    conditions: list[str],
    present_symptoms: set[str],
) -> SafetyReport:
    """Run all four checks against this patient's actual medicines."""
    medicines = resolve_medicines(medications)
    recognised = [m for m in medicines if m.recognised]

    report = SafetyReport(
        checked_medicines=[m.label for m in recognised],
        unrecognised=[m.label for m in medicines if not m.recognised],
    )

    report.findings.extend(_check_drug_allergy(recognised, allergies))
    report.findings.extend(_check_drug_drug(recognised))
    report.findings.extend(_check_drug_condition(recognised, conditions))
    report.findings.extend(_check_adverse_reactions(recognised, present_symptoms))

    # Most serious first.
    report.findings.sort(key=lambda f: -_RANK[f.severity])
    return report
