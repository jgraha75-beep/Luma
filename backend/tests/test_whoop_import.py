from copy import deepcopy

import pytest

from luma.services.whoop_import import WhoopBundleError, normalize_whoop_bundle
from tests.whoop_fixtures import WHOOP_BUNDLE


def test_normalizer_keeps_whoop_dimensions_separate_and_strips_identity():
    result = normalize_whoop_bundle(deepcopy(WHOOP_BUNDLE))

    assert result.status == "complete"
    assert {item.kind for item in result.observations} == {
        "recovery", "sleep", "cycle", "workout", "body_measurement",
    }
    assert all("user_id" not in item.payload for item in result.observations)
    assert all("metric" not in item.payload for item in result.observations)
    assert result.observations[0].external_id == "101"


def test_body_measurement_singleton_is_stored_as_current_snapshot():
    bundle = deepcopy(WHOOP_BUNDLE)
    bundle["collections"]["body_measurement"] = {
        "privacy_mode": "structured",
        "data": {"height_meter": 1.8, "weight_kilogram": 80.0, "max_heart_rate": 190},
    }

    result = normalize_whoop_bundle(bundle)
    body = next(item for item in result.observations if item.kind == "body_measurement")

    assert body.external_id == "current"
    assert body.payload == {"height_meter": 1.8, "weight_kilogram": 80.0, "max_heart_rate": 190}


def test_live_nested_score_fields_are_flattened_by_allowlist_contract():
    bundle = deepcopy(WHOOP_BUNDLE)
    bundle["collections"]["recovery"]["records"][0] = {
        "cycle_id": 202,
        "sleep_id": "sleep-202",
        "score_state": "SCORED",
        "score": {"recovery_score": 81, "hrv_rmssd_milli": 72.0},
    }

    result = normalize_whoop_bundle(bundle)
    recovery = next(item for item in result.observations if item.kind == "recovery" and item.external_id == "202")

    assert recovery.payload == {"recovery_score": 81, "hrv_rmssd_milli": 72.0}


def test_unscored_recovery_remains_unscored_without_invented_score():
    bundle = deepcopy(WHOOP_BUNDLE)
    record = bundle["collections"]["recovery"]["records"][0]
    record["score_state"] = "PENDING_SCORE"
    record.pop("recovery_score")

    result = normalize_whoop_bundle(bundle)
    recovery = next(item for item in result.observations if item.kind == "recovery")

    assert recovery.score_state == "PENDING_SCORE"
    assert "recovery_score" not in recovery.payload


def test_incomplete_pagination_is_partial_not_complete():
    bundle = deepcopy(WHOOP_BUNDLE)
    bundle["collections"]["workout"]["has_more"] = True
    bundle["collections"]["workout"]["next_token"] = "more"

    result = normalize_whoop_bundle(bundle)

    assert result.status == "partial"
    assert result.collections["workout"]["has_more"] is True


def test_raw_privacy_mode_is_rejected():
    bundle = deepcopy(WHOOP_BUNDLE)
    bundle["collections"]["sleep"]["privacy_mode"] = "raw"

    with pytest.raises(WhoopBundleError, match="raw WHOOP responses"):
        normalize_whoop_bundle(bundle)


def test_missing_record_id_is_skipped_and_reported():
    bundle = deepcopy(WHOOP_BUNDLE)
    bundle["collections"]["workout"]["records"][0].pop("id")

    result = normalize_whoop_bundle(bundle)

    assert result.status == "partial"
    assert result.collections["workout"]["skipped"] == 1
    assert not any(item.kind == "workout" for item in result.observations)
