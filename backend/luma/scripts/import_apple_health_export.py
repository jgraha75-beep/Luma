"""Import a bounded Apple Health ZIP history into Luma's biometric store.

This is a local, one-time backfill for the supported Luma biometrics. It
streams only ``Record`` and ``Workout``-free Apple Health XML, ignores clinical
and route files, and leaves the supplied export unchanged.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import xml.etree.ElementTree as element_tree
import zipfile
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from sqlalchemy import select

from luma.db.models import User
from luma.db.session import AsyncSessionLocal
from luma.services.biometric_store import persist_biometric_rows

logger = logging.getLogger(__name__)

_QUANTITY_MAP: dict[str, tuple[str, str]] = {
    "HKQuantityTypeIdentifierBodyMass": ("weight_kg", "mass"),
    "HKQuantityTypeIdentifierBodyMassIndex": ("bmi", "plain"),
    "HKQuantityTypeIdentifierBodyFatPercentage": ("body_fat_pct", "percentage"),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("hrv_ms", "plain"),
    "HKQuantityTypeIdentifierRestingHeartRate": ("rhr_bpm", "plain"),
    "HKQuantityTypeIdentifierWalkingHeartRateAverage": ("walking_hr_bpm", "plain"),
    "HKQuantityTypeIdentifierRespiratoryRate": ("respiratory_rate_bpm", "plain"),
    "HKQuantityTypeIdentifierOxygenSaturation": ("spo2_pct", "percentage"),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("active_kcal", "energy"),
    "HKQuantityTypeIdentifierBasalEnergyBurned": ("bmr_kcal", "energy"),
    "HKQuantityTypeIdentifierStepCount": ("steps", "plain"),
    "HKQuantityTypeIdentifierFlightsClimbed": ("flights_climbed", "plain"),
    "HKQuantityTypeIdentifierAppleExerciseTime": ("exercise_min", "minutes"),
    "HKQuantityTypeIdentifierAppleStandTime": ("stand_min", "minutes"),
    "HKQuantityTypeIdentifierDistanceWalkingRunning": ("distance_km", "distance"),
    "HKQuantityTypeIdentifierAppleStandHour": ("stand_hours", "plain"),
    "HKQuantityTypeIdentifierMindfulSession": ("mindful_min", "minutes"),
    "HKQuantityTypeIdentifierWalkingSpeed": ("walking_speed_kmh", "speed"),
    "HKQuantityTypeIdentifierWalkingStepLength": ("step_length_cm", "length"),
    "HKQuantityTypeIdentifierWalkingAsymmetryPercentage": ("walking_asymmetry_pct", "percentage"),
    "HKQuantityTypeIdentifierWalkingDoubleSupportPercentage": ("double_support_pct", "percentage"),
    "HKQuantityTypeIdentifierBodyTemperature": ("body_temp_c", "temperature"),
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": ("wrist_temp_c", "temperature"),
}

_SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"
_ASLEEP_VALUES = ("asleep", "core", "deep", "rem")


def parse_apple_timestamp(value: str) -> datetime:
    """Convert Apple Health's timestamp format to timezone-aware UTC."""
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z").astimezone(UTC)


def converted_value(value: float, unit: str, conversion: str) -> float | None:
    """Return Luma's canonical unit, or None for an unsupported source unit."""
    normalized = unit.lower()
    if conversion == "plain":
        return value
    if conversion == "mass":
        if normalized == "kg":
            return value
        if normalized in {"lb", "lbs"}:
            return value / 2.20462262
    elif conversion == "percentage":
        return value * 100 if normalized in {"count", "1"} and value <= 1 else value
    elif conversion == "energy":
        if normalized == "kcal":
            return value
        if normalized == "kj":
            return value / 4.184
    elif conversion == "minutes":
        if normalized in {"min", "minute", "minutes"}:
            return value
        if normalized in {"hr", "hour", "hours"}:
            return value * 60
    elif conversion == "distance":
        if normalized == "km":
            return value
        if normalized in {"mi", "mile", "miles"}:
            return value * 1.60934
        if normalized == "m":
            return value / 1000
    elif conversion == "speed":
        if normalized in {"km/hr", "km/h"}:
            return value
        if normalized == "mi/hr":
            return value * 1.60934
        if normalized == "m/s":
            return value * 3.6
    elif conversion == "length":
        if normalized == "cm":
            return value
        if normalized == "m":
            return value * 100
        if normalized == "in":
            return value * 2.54
    elif conversion == "temperature":
        if normalized == "degc":
            return value
        if normalized == "degf":
            return (value - 32) * 5 / 9
    return None


def _row(user_id: str, timestamp: datetime, metric: str, value: float, source: str, source_type: str, unit: str) -> dict:
    return {
        "user_id": user_id,
        "ts": timestamp,
        "metric": metric,
        "value": value,
        "source": source or "Apple Health",
        "source_meta": {
            "apple_health_type": source_type,
            "apple_health_unit": unit,
            "import_kind": "local_one_time_backfill",
        },
    }


def iter_apple_health_rows(export_zip: Path, user_id: str, since: datetime) -> Iterable[dict]:
    """Yield supported Luma rows from the export without loading its XML into memory."""
    with zipfile.ZipFile(export_zip) as archive:
        xml_names = [name for name in archive.namelist() if name.endswith("export.xml")]
        if len(xml_names) != 1:
            raise ValueError("Apple Health ZIP must contain exactly one export.xml file")
        with archive.open(xml_names[0]) as xml_file:
            for _, element in element_tree.iterparse(xml_file, events=("end",)):
                if element.tag != "Record":
                    element.clear()
                    continue
                try:
                    record_type = element.attrib["type"]
                    start = parse_apple_timestamp(element.attrib["startDate"])
                    if start < since:
                        continue
                    source = element.attrib.get("sourceName", "Apple Health")
                    unit = element.attrib.get("unit", "")
                    if record_type == _SLEEP_TYPE:
                        end = parse_apple_timestamp(element.attrib["endDate"])
                        duration_minutes = (end - start).total_seconds() / 60
                        value = element.attrib.get("value", "").lower()
                        if duration_minutes <= 0:
                            continue
                        if "inbed" in value.replace(" ", ""):
                            yield _row(user_id, start, "sleep_duration_min", duration_minutes, source, record_type, "min")
                        elif any(stage in value for stage in _ASLEEP_VALUES):
                            yield _row(user_id, start, "sleep_asleep_min", duration_minutes, source, record_type, "min")
                        continue
                    mapped = _QUANTITY_MAP.get(record_type)
                    if not mapped:
                        continue
                    internal_metric, conversion = mapped
                    converted = converted_value(float(element.attrib["value"]), unit, conversion)
                    if converted is not None:
                        yield _row(user_id, start, internal_metric, converted, source, record_type, unit)
                except (KeyError, TypeError, ValueError):
                    logger.debug("Skipping malformed Apple Health record type=%s", element.attrib.get("type", "unknown"))
                finally:
                    element.clear()


async def import_export(export_zip: Path, email: str, since: datetime, *, dry_run: bool, batch_size: int) -> Counter[str]:
    """Resolve one owner account and import rows in bounded, idempotent batches."""
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            raise ValueError("No Luma account matches the supplied email")
        rows = iter_apple_health_rows(export_zip, str(user.id), since)
        counts: Counter[str] = Counter()
        batch: list[dict] = []
        for row in rows:
            counts[row["metric"]] += 1
            if dry_run:
                continue
            batch.append(row)
            if len(batch) >= batch_size:
                await persist_biometric_rows(batch, db, user.id, source_ecosystem="apple_health", data_source=user.data_source)
                batch = []
        if batch and not dry_run:
            await persist_biometric_rows(batch, db, user.id, source_ecosystem="apple_health", data_source=user.data_source)
        return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Locally backfill supported Apple Health biometrics into Luma.")
    parser.add_argument("export_zip", type=Path)
    parser.add_argument("--email", required=True, help="Existing local Luma account email.")
    parser.add_argument("--since", type=date.fromisoformat, default=date.today() - timedelta(days=365), help="Inclusive YYYY-MM-DD lower bound; defaults to one year.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and count eligible rows without writing Luma data.")
    parser.add_argument("--batch-size", type=int, default=5000)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if not args.export_zip.is_file():
        raise SystemExit("Apple Health export ZIP was not found")
    if args.batch_size < 1 or args.batch_size > 10_000:
        raise SystemExit("--batch-size must be between 1 and 10000")
    since = datetime(args.since.year, args.since.month, args.since.day, tzinfo=UTC)
    counts = await import_export(args.export_zip, args.email, since, dry_run=args.dry_run, batch_size=args.batch_size)
    mode = "Dry run" if args.dry_run else "Imported"
    print(f"{mode} {sum(counts.values())} supported Apple Health rows since {args.since.isoformat()}")
    for metric, count in sorted(counts.items()):
        print(f"{metric}: {count}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(main())
