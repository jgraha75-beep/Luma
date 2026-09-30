from luma.scripts.import_apple_health_export import converted_value, parse_apple_timestamp


def test_parse_apple_timestamp_normalizes_to_utc():
    assert parse_apple_timestamp("2026-09-01 03:12:00 -0500").isoformat() == "2026-09-01T08:12:00+00:00"


def test_unit_conversions_are_canonical():
    assert round(converted_value(220.462262, "lb", "mass") or 0, 2) == 100
    assert converted_value(0.97, "count", "percentage") == 97
    assert round(converted_value(1, "mi", "distance") or 0, 5) == 1.60934


def test_unsupported_units_do_not_enter_luma():
    assert converted_value(100, "cups", "mass") is None
