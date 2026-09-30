"""Per-user nutrition focus presets and validation.

The focus contract controls which nutrition metrics the UI and later coaching
features should emphasize. It is intentionally independent from the user's
numeric goals: a metric can be visible without having a target yet.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


NUTRITION_FOCUS_KIND = "nutrition_focus"
DEFAULT_PRESET = "ldl_support"

FocusPreset = Literal["ldl_support", "performance", "comprehensive", "custom"]


class FocusMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    unit: str
    direction: Literal["min", "max", "info"]


METRICS: tuple[FocusMetric, ...] = (
    FocusMetric(id="calories", label="Calories", unit="kcal", direction="info"),
    FocusMetric(id="protein_g", label="Protein", unit="g", direction="min"),
    FocusMetric(id="carbohydrates_g", label="Carbohydrates", unit="g", direction="info"),
    FocusMetric(id="fat_g", label="Total fat", unit="g", direction="info"),
    FocusMetric(id="saturated_fat_g", label="Saturated fat", unit="g", direction="max"),
    FocusMetric(id="soluble_fiber_g", label="Soluble fiber", unit="g", direction="min"),
    FocusMetric(id="sodium_mg", label="Sodium", unit="mg", direction="max"),
    FocusMetric(id="sugars_g", label="Total sugar", unit="g", direction="info"),
    FocusMetric(id="added_sugars_g", label="Added sugar", unit="g", direction="max"),
    FocusMetric(id="cholesterol_mg", label="Cholesterol", unit="mg", direction="max"),
)
METRIC_BY_ID = {metric.id: metric for metric in METRICS}

PRESET_METRICS: dict[str, tuple[str, ...]] = {
    "ldl_support": (
        "calories", "saturated_fat_g", "soluble_fiber_g", "sodium_mg", "protein_g",
    ),
    "performance": ("calories", "protein_g", "carbohydrates_g", "fat_g"),
    "comprehensive": tuple(metric.id for metric in METRICS),
}


class NutritionFocus(BaseModel):
    """Canonical persisted focus selection returned by the settings API."""

    preset: FocusPreset
    metrics: list[str] = Field(min_length=1, max_length=len(METRICS))

    @field_validator("metrics")
    @classmethod
    def validate_metrics(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("metrics must not contain duplicates")
        unknown = [value for value in values if value not in METRIC_BY_ID]
        if unknown:
            raise ValueError(f"unknown nutrition metrics: {', '.join(unknown)}")
        return values

    @model_validator(mode="after")
    def validate_preset(self) -> "NutritionFocus":
        if self.preset != "custom":
            expected = PRESET_METRICS[self.preset]
            if tuple(self.metrics) != expected:
                raise ValueError(f"metrics must match the {self.preset} preset")
        return self


def default_focus() -> NutritionFocus:
    return NutritionFocus(preset=DEFAULT_PRESET, metrics=list(PRESET_METRICS[DEFAULT_PRESET]))


def focus_from_preference(value: str | None) -> NutritionFocus:
    """Decode stored preference JSON, falling back safely on old/bad values."""
    if not value:
        return default_focus()
    try:
        import json

        raw: Any = json.loads(value)
        if not isinstance(raw, dict):
            return default_focus()
        return NutritionFocus.model_validate(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default_focus()


def preference_value(focus: NutritionFocus) -> str:
    import json

    return json.dumps(focus.model_dump(), separators=(",", ":"))


def catalog() -> dict[str, Any]:
    return {
        "presets": [
            {"id": "ldl_support", "label": "LDL support", "description": "Prioritize cholesterol-related nutrition signals."},
            {"id": "performance", "label": "Performance macros", "description": "Prioritize calories, protein, carbohydrates, and total fat."},
            {"id": "comprehensive", "label": "All nutrition", "description": "Show every supported nutrition metric."},
            {"id": "custom", "label": "Custom", "description": "Choose the metrics that matter to you."},
        ],
        "metrics": [metric.model_dump() for metric in METRICS],
    }
