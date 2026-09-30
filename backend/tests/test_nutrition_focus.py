import json

import pytest
from pydantic import ValidationError

from luma.services.nutrition_focus import (
    NutritionFocus,
    PRESET_METRICS,
    default_focus,
    focus_from_preference,
    preference_value,
)


def test_default_focus_preserves_existing_ldl_orientation():
    focus = default_focus()
    assert focus.preset == "ldl_support"
    assert focus.metrics == list(PRESET_METRICS["ldl_support"])


def test_performance_preset_supports_standard_macros():
    focus = NutritionFocus(preset="performance", metrics=list(PRESET_METRICS["performance"]))
    assert focus.metrics == ["calories", "protein_g", "carbohydrates_g", "fat_g"]


def test_custom_focus_rejects_unknown_and_duplicate_metrics():
    with pytest.raises(ValidationError, match="unknown nutrition metrics"):
        NutritionFocus(preset="custom", metrics=["protein_g", "not_a_metric"])
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        NutritionFocus(preset="custom", metrics=["protein_g", "protein_g"])


def test_non_custom_focus_cannot_override_preset_metrics():
    with pytest.raises(ValidationError, match="must match the performance preset"):
        NutritionFocus(preset="performance", metrics=["protein_g"])


def test_preference_round_trip_is_compact_and_canonical():
    focus = NutritionFocus(preset="custom", metrics=["protein_g", "fat_g"])
    stored = preference_value(focus)
    assert json.loads(stored) == {"preset": "custom", "metrics": ["protein_g", "fat_g"]}
    assert focus_from_preference(stored) == focus


@pytest.mark.parametrize("value", [None, "", "not-json", "[]", '{"preset":"custom","metrics":[]}'])
def test_invalid_stored_preference_falls_back_to_default(value):
    assert focus_from_preference(value) == default_focus()
