"""Diet and lifestyle guidance. Pipeline step 9.

Templates, not LLM invention. Every item is filtered against the patient's
diet type, allergies and existing conditions before it is shown:

    a vegetarian is never told to eat chicken soup
    a diabetic is never told to drink fruit juice or take honey
    a hypertensive is never told to drink salted lassi

That filtering is what makes acceptance test 10 work -- two patients with
identical symptoms get visibly different advice.
"""
from dataclasses import dataclass, field

from core import knowledge


class Category:
    DIET_PREFER = "diet_prefer"
    DIET_AVOID = "diet_avoid"
    HYDRATION = "hydration"
    LIFESTYLE = "lifestyle"
    MONITOR = "monitor"
    WARNING_SIGN = "warning_sign"


SECTION_TO_CATEGORY = {
    "prefer": Category.DIET_PREFER,
    "avoid": Category.DIET_AVOID,
    "hydration": Category.HYDRATION,
    "lifestyle": Category.LIFESTYLE,
    "monitor": Category.MONITOR,
    "warning_signs": Category.WARNING_SIGN,
}

# Tags a given diet type cannot have.
DIET_EXCLUSIONS = {
    "veg": {"contains_meat"},
    "vegan": {"contains_meat", "contains_egg", "contains_dairy"},
    "jain": {"contains_meat", "contains_egg", "contains_root"},
    "non_veg": set(),
}

# Tags a given condition rules out. Keys are matched as substrings, so
# "Type 2 Diabetes" matches "diabet".
CONDITION_EXCLUSIONS = {
    "diabet": {"high_sugar"},
    "hypertens": {"high_salt"},
    "high blood pressure": {"high_salt"},
    "kidney": {"high_potassium", "high_salt"},
    "renal": {"high_potassium", "high_salt"},
    "heart failure": {"high_salt"},
}


@dataclass
class Recommendation:
    category: str
    text: str


@dataclass
class GuidancePlan:
    recommendations: list[Recommendation] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    suppressed_count: int = 0

    def by_category(self, category: str) -> list[str]:
        return [r.text for r in self.recommendations if r.category == category]


def _excluded_tags(diet_type: str, conditions: list[str]) -> set[str]:
    excluded = set(DIET_EXCLUSIONS.get(diet_type, set()))
    lowered = [c.lower() for c in conditions]
    for keyword, tags in CONDITION_EXCLUSIONS.items():
        if any(keyword in c for c in lowered):
            excluded |= tags
    return excluded


def _allergen_conflict(text: str, allergens: list[str]) -> bool:
    """Drop any suggestion naming something the patient is allergic to."""
    lowered = text.lower()
    for allergen in allergens:
        token = allergen.strip().lower()
        if len(token) >= 4 and token in lowered:
            return True
    return False


def build(
    condition_codes: list[str],
    diet_type: str = "veg",
    conditions: list[str] | None = None,
    allergens: list[str] | None = None,
) -> GuidancePlan:
    """Build filtered guidance for the surviving candidate conditions."""
    conditions = conditions or []
    allergens = allergens or []
    excluded = _excluded_tags(diet_type, conditions)

    plan = GuidancePlan()
    seen: set[tuple[str, str]] = set()
    templates = knowledge.diet_templates()

    def add(section: str, items: list[dict]) -> None:
        category = SECTION_TO_CATEGORY.get(section)
        if category is None:
            return
        for item in items:
            text = item.get("text", "").strip()
            if not text:
                continue
            tags = set(item.get("tags", []))
            if tags & excluded:
                plan.suppressed_count += 1
                continue
            if _allergen_conflict(text, allergens):
                plan.suppressed_count += 1
                continue
            key = (category, text)
            if key in seen:
                continue
            seen.add(key)
            plan.recommendations.append(Recommendation(category=category, text=text))

    for code in condition_codes:
        template = templates.get(code)
        if template is None:
            continue
        if template.source_url and template.source_url not in plan.sources:
            plan.sources.append(template.source_url)
        for section, items in template.sections.items():
            add(section, items)

    # Generic advice fills the gaps, and covers the no-candidate case.
    for section, items in knowledge.diet_defaults().items():
        add(section, items)

    return plan
