"""
Map Plant.id health assessment JSON → fertigation pump decision.
Also extracts specific nutrient deficiency labels (N/P/K/Fe/...).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any


# Keywords that suggest nutrient-related stress (trigger fertigation).
NUTRIENT_KEYWORDS = (
    "nitrogen",
    "phosphorus",
    "potassium",
    "iron",
    "magnesium",
    "calcium",
    "manganese",
    "zinc",
    "boron",
    "sulfur",
    "sulphur",
    "nutrient",
    "deficiency",
    "chlorosis",
    "yellow",
    "pale",
)

# Ordered matching for specific nutrient type extraction.
NUTRIENT_TYPES: list[tuple[str, tuple[str, ...]]] = [
    ("Nitrogen (N)", ("nitrogen", " n deficiency", "n-deficiency", "lack of nitrogen")),
    ("Phosphorus (P)", ("phosphorus", "phosphorous", " p deficiency", "lack of phosphorus")),
    ("Potassium (K)", ("potassium", " k deficiency", "lack of potassium", "potash")),
    ("Iron (Fe)", ("iron", "fe deficiency", "lack of iron", "iron chlorosis")),
    ("Magnesium (Mg)", ("magnesium", "mg deficiency", "lack of magnesium")),
    ("Calcium (Ca)", ("calcium", "ca deficiency", "lack of calcium")),
    ("Manganese (Mn)", ("manganese", "mn deficiency")),
    ("Zinc (Zn)", ("zinc", "zn deficiency")),
    ("Boron (B)", ("boron", " b deficiency")),
    ("Sulfur (S)", ("sulfur", "sulphur", "s deficiency")),
]


@dataclass
class DoseDecision:
    is_healthy: bool
    should_dose: bool
    severity_pct: int
    dose_ms: int
    top_issue: str
    top_probability: float
    reason: str
    treatment_hint: str
    raw_suggestions: list[dict[str, Any]]
    nutrient_deficient: str = "None"
    nutrient_candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def classify_nutrient(text: str) -> str | None:
    t = f" {text.lower()} "
    for label, keys in NUTRIENT_TYPES:
        if any(k in t for k in keys):
            return label
    if "deficiency" in t or "chlorosis" in t or "nutrient" in t:
        return "Nutrient deficiency (unspecified)"
    return None


def decide_dose(
    health_json: dict[str, Any],
    *,
    dose_ms_base: int = 3000,
    dose_ms_max: int = 12000,
    severity_min: int = 35,
    healthy_probability_min: float = 0.55,
    prefer_nutrient_issues: bool = True,
) -> DoseDecision:
    """
    Convert Plant.id health_assessment response into pump timing.
    """
    result = health_json.get("result") or {}
    is_healthy_block = result.get("is_healthy") or {}
    is_healthy = bool(is_healthy_block.get("binary", False))
    healthy_prob = float(is_healthy_block.get("probability") or 0.0)

    suggestions = ((result.get("disease") or {}).get("suggestions")) or []
    parsed: list[dict[str, Any]] = []
    nutrient_candidates: list[dict[str, Any]] = []

    for s in suggestions:
        name = str(s.get("name") or "unknown")
        prob = float(s.get("probability") or 0.0)
        details = s.get("details") or {}
        description = str(details.get("description") or "")
        treatment = details.get("treatment") or {}
        if isinstance(treatment, dict):
            parts = []
            for key in ("biological", "chemical", "prevention"):
                vals = treatment.get(key) or []
                if isinstance(vals, list):
                    parts.extend(str(v) for v in vals[:2])
            treatment_text = "; ".join(parts)
        else:
            treatment_text = str(treatment)

        blob = f"{name} {description}"
        nutrient_label = classify_nutrient(blob)
        is_nutrient_like = nutrient_label is not None or any(
            k in blob.lower() for k in NUTRIENT_KEYWORDS
        )

        item = {
            "name": name,
            "probability": prob,
            "description": description,
            "treatment": treatment_text,
            "is_nutrient_like": is_nutrient_like,
            "nutrient_label": nutrient_label,
        }
        parsed.append(item)
        if nutrient_label:
            nutrient_candidates.append(
                {
                    "nutrient": nutrient_label,
                    "source_issue": name,
                    "probability": prob,
                }
            )

    # Deduplicate nutrients keeping highest probability
    best_by_nutrient: dict[str, dict[str, Any]] = {}
    for c in nutrient_candidates:
        key = c["nutrient"]
        if key not in best_by_nutrient or c["probability"] > best_by_nutrient[key]["probability"]:
            best_by_nutrient[key] = c
    nutrient_candidates = sorted(
        best_by_nutrient.values(), key=lambda x: x["probability"], reverse=True
    )

    if is_healthy and healthy_prob >= healthy_probability_min:
        return DoseDecision(
            is_healthy=True,
            should_dose=False,
            severity_pct=int(round((1.0 - healthy_prob) * 100)),
            dose_ms=0,
            top_issue="healthy",
            top_probability=healthy_prob,
            reason="Plant.id reports healthy plant",
            treatment_hint="",
            raw_suggestions=parsed,
            nutrient_deficient="None",
            nutrient_candidates=[],
        )

    candidates = parsed
    if prefer_nutrient_issues:
        nutrient_hits = [p for p in parsed if p["is_nutrient_like"]]
        if nutrient_hits:
            candidates = nutrient_hits

    if not candidates:
        severity = int(round((1.0 - healthy_prob) * 100))
        dose = 0
        if severity >= severity_min:
            scale = severity / 100.0
            dose = int(dose_ms_base + scale * (dose_ms_max - dose_ms_base))
        return DoseDecision(
            is_healthy=False,
            should_dose=dose > 0,
            severity_pct=severity,
            dose_ms=dose,
            top_issue="unspecified_stress",
            top_probability=1.0 - healthy_prob,
            reason="Unhealthy with no disease suggestions; using healthy-probability gap",
            treatment_hint="",
            raw_suggestions=parsed,
            nutrient_deficient="Unspecified stress",
            nutrient_candidates=nutrient_candidates,
        )

    top = max(candidates, key=lambda p: p["probability"])
    severity = int(round(_clamp(top["probability"], 0.0, 1.0) * 100))
    dose = 0
    if severity >= severity_min:
        scale = severity / 100.0
        dose = int(dose_ms_base + scale * (dose_ms_max - dose_ms_base))
        dose = min(dose, dose_ms_max)

    nutrient = top.get("nutrient_label") or (
        nutrient_candidates[0]["nutrient"] if nutrient_candidates else "Not nutrient-specific"
    )

    return DoseDecision(
        is_healthy=False,
        should_dose=dose > 0,
        severity_pct=severity,
        dose_ms=dose,
        top_issue=top["name"],
        top_probability=top["probability"],
        reason=f"Plant.id issue '{top['name']}' prob={top['probability']:.2%}",
        treatment_hint=top.get("treatment") or "",
        raw_suggestions=parsed,
        nutrient_deficient=nutrient,
        nutrient_candidates=nutrient_candidates,
    )
