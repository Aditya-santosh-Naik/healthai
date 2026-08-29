"""Loads all clinical knowledge from data/*.yaml.

No clinical rule is hardcoded in Python. Code reads data. Everything is cached
at import time; the files never change at runtime.
"""
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from config import DATA_DIR
from core.text_norm import canonicalise, expand_alias_contractions


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# --- symptoms ---------------------------------------------------------------

@dataclass(frozen=True)
class Symptom:
    code: str
    display: str
    aliases: tuple[str, ...]


@lru_cache(maxsize=1)
def symptoms() -> dict[str, Symptom]:
    raw = _load_yaml(DATA_DIR / "symptoms.yaml")["symptoms"]
    return {
        code: Symptom(
            code=code,
            display=spec.get("display", code.replace("_", " ").capitalize()),
            aliases=tuple(spec.get("aliases", [])),
        )
        for code, spec in raw.items()
    }


@lru_cache(maxsize=1)
def alias_index() -> list[tuple[str, str]]:
    """(canonical alias, symptom_code) sorted longest-first.

    Order matters: "dry cough" must win over "cough", and "severe headache"
    over "headache". Aliases are canonicalised the same way as input text, and
    contracted spellings get an expanded twin so "cant smell" also matches
    "can not smell".
    """
    raw: list[tuple[str, str]] = []
    for code, symptom in symptoms().items():
        for alias in symptom.aliases:
            raw.append((alias, code))
        raw.append((code.replace("_", " "), code))

    pairs: list[tuple[str, str]] = []
    for alias, code in raw:
        lowered = alias.lower().strip()
        pairs.append((canonicalise(lowered), code))
        expanded = expand_alias_contractions(lowered)
        if expanded:
            pairs.append((canonicalise(expanded), code))

    # Longest alias first; stable tie-break on the alias text.
    pairs.sort(key=lambda p: (-len(p[0]), p[0]))
    # Deduplicate, keeping the first (longest) binding for an alias.
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for alias, code in pairs:
        if alias and alias not in seen:
            seen.add(alias)
            unique.append((alias, code))
    return unique


@lru_cache(maxsize=1)
def implications() -> dict[str, tuple[str, ...]]:
    """symptom -> broader symptoms it entails. Positive findings only."""
    raw = _load_yaml(DATA_DIR / "symptoms.yaml").get("implications", {})
    return {code: tuple(parents) for code, parents in raw.items()}


def expand_implied(codes: set[str]) -> set[str]:
    """Close a set of positive symptom codes over the implication graph."""
    table = implications()
    expanded = set(codes)
    queue = list(codes)
    while queue:
        current = queue.pop()
        for parent in table.get(current, ()):
            if parent not in expanded:
                expanded.add(parent)
                queue.append(parent)
    return expanded


def display_name(code: str) -> str:
    s = symptoms().get(code)
    return s.display if s else code.replace("_", " ").capitalize()


# --- conditions -------------------------------------------------------------

@dataclass(frozen=True)
class Condition:
    code: str
    display_name: str
    # Prevalence tier, not a probability. Names a band in
    # evidence_engine.BASE_RATE_PRIOR rather than carrying a number, so the
    # weights stay in one place and the YAML stays readable.
    base_rate: str
    base_rate_source: str
    sources: tuple[dict[str, str], ...]
    hallmark: tuple[str, ...]
    supporting: tuple[str, ...]
    expected: tuple[str, ...]
    contradictory: tuple[str, ...]
    duration_min_hours: float | None
    duration_max_hours: float | None
    context_modifiers: tuple[dict[str, str], ...]
    red_flags: tuple[str, ...]

    @property
    def all_symptoms(self) -> set[str]:
        return set(self.hallmark) | set(self.supporting) | set(self.expected)


@lru_cache(maxsize=1)
def conditions() -> dict[str, Condition]:
    out: dict[str, Condition] = {}
    for path in sorted((DATA_DIR / "conditions").glob("*.yaml")):
        raw = _load_yaml(path)
        duration = raw.get("typical_duration_hours") or {}
        out[raw["code"]] = Condition(
            code=raw["code"],
            display_name=raw["display_name"],
            base_rate=raw["base_rate"],
            base_rate_source=raw["base_rate_source"],
            sources=tuple(raw.get("sources", [])),
            hallmark=tuple(raw.get("hallmark_symptoms", [])),
            supporting=tuple(raw.get("supporting_symptoms", [])),
            expected=tuple(raw.get("expected_symptoms", [])),
            contradictory=tuple(raw.get("contradictory_symptoms", [])),
            duration_min_hours=duration.get("min"),
            duration_max_hours=duration.get("max"),
            context_modifiers=tuple(raw.get("context_modifiers", [])),
            red_flags=tuple(raw.get("red_flags", [])),
        )
    return out


# --- red flags --------------------------------------------------------------

@dataclass(frozen=True)
class RedFlag:
    code: str
    urgency: str
    any_of: tuple[str, ...]
    all_of: tuple[str, ...]
    message: str
    action: str
    source_name: str
    source_url: str


@lru_cache(maxsize=1)
def red_flags() -> tuple[RedFlag, ...]:
    raw = _load_yaml(DATA_DIR / "red_flags.yaml")["red_flags"]
    flags = [
        RedFlag(
            code=r["code"],
            urgency=r.get("urgency", "urgent"),
            any_of=tuple(r.get("any_of", [])),
            all_of=tuple(r.get("all_of", [])),
            message=r["message"].strip(),
            action=r["action"].strip(),
            source_name=r.get("source_name", ""),
            source_url=r.get("source_url", ""),
        )
        for r in raw
    ]
    # Emergencies before urgent, and combination rules before single-symptom
    # ones, so the most specific message is the one the patient sees.
    flags.sort(key=lambda f: (f.urgency != "emergency", not f.all_of))
    return tuple(flags)


@lru_cache(maxsize=1)
def screening_questions() -> tuple[str, ...]:
    """Red-flag symptoms worth asking about, in priority order."""
    raw = _load_yaml(DATA_DIR / "red_flags.yaml")
    return tuple(raw.get("screening_questions", []))


@lru_cache(maxsize=1)
def max_safety_questions() -> int:
    raw = _load_yaml(DATA_DIR / "red_flags.yaml")
    return int(raw.get("max_safety_questions", 2))


# --- drugs ------------------------------------------------------------------

@dataclass(frozen=True)
class Drug:
    generic: str
    display: str
    brands: tuple[str, ...]
    drug_class: str
    otc: bool
    side_effects: tuple[str, ...]
    source_url: str


@lru_cache(maxsize=1)
def drugs() -> dict[str, Drug]:
    raw = _load_yaml(DATA_DIR / "drugs.yaml")["drugs"]
    return {
        d["generic"]: Drug(
            generic=d["generic"],
            display=d.get("display", d["generic"]),
            brands=tuple(d.get("brands", [])),
            drug_class=d.get("drug_class", "unknown"),
            otc=bool(d.get("otc", False)),
            side_effects=tuple(d.get("side_effects", [])),
            source_url=d.get("source_url", ""),
        )
        for d in raw
    }


@lru_cache(maxsize=1)
def brand_to_generic() -> dict[str, str]:
    """Lowercased brand and generic names -> generic key.

    "Dolo 650", "dolo", "Crocin" all have to reach paracetamol.
    """
    index: dict[str, str] = {}
    for generic, drug in drugs().items():
        index[generic.lower()] = generic
        index[drug.display.lower()] = generic
        for brand in drug.brands:
            index[brand.lower()] = generic
            # "Dolo 650" should also match a bare "dolo".
            first = brand.split()[0].lower()
            index.setdefault(first, generic)
    return index


def resolve_drug(name: str | None) -> Drug | None:
    """Best-effort brand/generic resolution. Returns None if unrecognised."""
    if not name:
        return None
    key = name.strip().lower()
    generic = brand_to_generic().get(key)
    if generic is None:
        # Try the first word: "Pan-D 40mg" -> "pan-d" -> "pan".
        head = key.replace("-", " ").split()
        for token_count in (2, 1):
            candidate = " ".join(head[:token_count])
            if candidate in brand_to_generic():
                generic = brand_to_generic()[candidate]
                break
    return drugs().get(generic) if generic else None


# --- interactions -----------------------------------------------------------

@dataclass(frozen=True)
class Interaction:
    subject: str
    object: str
    type: str
    severity: str
    reason: str
    source_url: str


@dataclass(frozen=True)
class CrossReactivity:
    key: str
    display: str
    flags_classes: tuple[str, ...]
    also_caution_classes: tuple[str, ...]
    note: str
    source_url: str


@lru_cache(maxsize=1)
def interactions() -> tuple[Interaction, ...]:
    raw = _load_yaml(DATA_DIR / "interactions.yaml")["interactions"]
    return tuple(
        Interaction(
            subject=r["subject"],
            object=r["object"],
            type=r["type"],
            severity=r["severity"],
            reason=" ".join(r["reason"].split()),
            source_url=r.get("source_url", ""),
        )
        for r in raw
    )


@lru_cache(maxsize=1)
def cross_reactivity() -> dict[str, CrossReactivity]:
    raw = _load_yaml(DATA_DIR / "interactions.yaml")["allergy_cross_reactivity"]
    return {
        key: CrossReactivity(
            key=key,
            display=spec.get("display", key),
            flags_classes=tuple(spec.get("flags_classes", [])),
            also_caution_classes=tuple(spec.get("also_caution_classes", [])),
            note=" ".join(spec.get("note", "").split()),
            source_url=spec.get("source_url", ""),
        )
        for key, spec in raw.items()
    }


# --- diet templates ---------------------------------------------------------

@dataclass
class DietTemplate:
    source_url: str
    sections: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@lru_cache(maxsize=1)
def diet_templates() -> dict[str, DietTemplate]:
    raw = _load_yaml(DATA_DIR / "diet_templates.yaml")
    out: dict[str, DietTemplate] = {}
    for code, spec in raw.get("conditions", {}).items():
        sections = {
            key: list(value)
            for key, value in spec.items()
            if key != "source_url" and isinstance(value, list)
        }
        out[code] = DietTemplate(source_url=spec.get("source_url", ""), sections=sections)
    return out


@lru_cache(maxsize=1)
def diet_defaults() -> dict[str, list[dict[str, Any]]]:
    raw = _load_yaml(DATA_DIR / "diet_templates.yaml")
    return raw.get("defaults", {})
