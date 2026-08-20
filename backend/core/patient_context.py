"""Merge the stored patient profile into a form the engines can use.

Pipeline step 3. Only confirmed profile facts are used (spec section 15):
past consultations are history and are never auto-promoted to medical fact.
"""
from dataclasses import dataclass, field
from datetime import date

from core import knowledge
from core.evidence_engine import PatientContext

# Indian monsoon, roughly. Strengthens dengue and malaria candidates.
MONSOON_MONTHS = {6, 7, 8, 9, 10}

NSAID_CLASS = "nsaid"


@dataclass
class ProfileFacts:
    """Everything the pipeline needs from a patient profile."""

    name: str = ""
    age: int | None = None
    sex: str = ""
    diet_type: str = "veg"
    smoker: bool = False
    alcohol: bool = False
    conditions: list[str] = field(default_factory=list)
    allergens: list[str] = field(default_factory=list)
    allergies: list[dict[str, str | None]] = field(default_factory=list)
    medications: list[dict[str, str | None]] = field(default_factory=list)

    @property
    def medicine_labels(self) -> list[str]:
        return [
            (m.get("brand_name") or m.get("generic_name") or "").strip()
            for m in self.medications
            if (m.get("brand_name") or m.get("generic_name"))
        ]

    @property
    def on_nsaid(self) -> bool:
        for medication in self.medications:
            drug = knowledge.resolve_drug(
                medication.get("brand_name")
            ) or knowledge.resolve_drug(medication.get("generic_name"))
            if drug and drug.drug_class == NSAID_CLASS:
                return True
        return False

    def to_evidence_context(self, today: date | None = None) -> PatientContext:
        today = today or date.today()
        return PatientContext(
            age=self.age,
            smoker=self.smoker,
            alcohol=self.alcohol,
            conditions=list(self.conditions),
            on_nsaid=self.on_nsaid,
            monsoon_season=today.month in MONSOON_MONTHS,
        )


def from_profile(profile) -> ProfileFacts:
    """Build ProfileFacts from a SQLAlchemy PatientProfile.

    Only medicines the patient is actually taking are considered for safety
    checks -- a drug they were prescribed but stopped cannot interact.
    """
    active_conditions = [
        c.condition_name for c in profile.conditions if c.status == "active"
    ]
    taking = [
        m for m in profile.medications if m.status != "prescribed_not_taking"
    ]

    return ProfileFacts(
        name=profile.name,
        age=profile.age,
        sex=profile.sex,
        diet_type=profile.diet_type,
        smoker=bool(profile.smoker),
        alcohol=bool(profile.alcohol),
        conditions=active_conditions,
        allergens=[a.allergen for a in profile.allergies],
        allergies=[
            {"allergen": a.allergen, "allergen_class": a.allergen_class}
            for a in profile.allergies
        ],
        medications=[
            {
                "brand_name": m.brand_name,
                "generic_name": m.generic_name,
                "dose": m.dose,
                "frequency": m.frequency,
            }
            for m in taking
        ],
    )
