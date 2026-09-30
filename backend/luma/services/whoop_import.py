"""Normalize and persist read-only WHOOP collection data.

WHOOP observations intentionally live outside ``biometrics``.  A WHOOP strain
or recovery score is not an Apple Health quantity and must not be converted
into one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from luma.db.models import WhoopObservation, WhoopSyncRun


WHOOP_KINDS = ("recovery", "sleep", "cycle", "workout", "body_measurement")

_PAYLOAD_FIELDS: dict[str, tuple[str, ...]] = {
    "recovery": (
        "recovery_score", "resting_heart_rate", "hrv_rmssd_milli",
        "spo2_percentage", "skin_temp_celsius", "user_calibrating",
    ),
    "sleep": (
        "nap", "sleep_performance_percentage", "sleep_consistency_percentage",
        "sleep_efficiency_percentage", "respiratory_rate",
        "total_in_bed_time_milli", "total_awake_time_milli",
        "total_light_sleep_time_milli", "total_slow_wave_sleep_time_milli",
        "total_rem_sleep_time_milli", "disturbance_count",
        "baseline_milli", "need_from_sleep_debt_milli",
        "need_from_recent_strain_milli", "need_from_recent_nap_milli",
    ),
    "cycle": ("strain", "average_heart_rate", "max_heart_rate", "kilojoule"),
    "workout": (
        "sport_name", "strain", "average_heart_rate", "max_heart_rate",
        "kilojoule", "percent_recorded", "distance_meter",
        "altitude_gain_meter", "zone_zero_milli", "zone_one_milli",
        "zone_two_milli", "zone_three_milli", "zone_four_milli",
        "zone_five_milli",
    ),
    "body_measurement": ("height_meter", "weight_kilogram", "max_heart_rate"),
}


class WhoopBundleError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedWhoopObservation:
    kind: str
    external_id: str
    start_ts: datetime | None
    end_ts: datetime | None
    score_state: str | None
    payload: dict[str, Any]
    source_updated_at: datetime | None


@dataclass(frozen=True)
class NormalizedWhoopBundle:
    pulled_at: datetime
    window_start: datetime | None
    window_end: datetime | None
    status: str
    collections: dict[str, dict[str, Any]]
    observations: tuple[NormalizedWhoopObservation, ...]


def _timestamp(value: Any, *, required: bool = False) -> datetime | None:
    if value in (None, ""):
        if required:
            raise WhoopBundleError("missing required timestamp")
        return None
    if not isinstance(value, str):
        raise WhoopBundleError("timestamps must be ISO-8601 strings")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WhoopBundleError(f"invalid timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise WhoopBundleError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _external_id(kind: str, record: dict[str, Any]) -> str | None:
    if kind == "recovery":
        value = record.get("cycle_id") or record.get("sleep_id")
    elif kind == "body_measurement":
        # WHOOP exposes the authenticated user's current measurements as a
        # singleton resource rather than a versioned collection.
        value = "current"
    else:
        value = record.get("id")
    if value in (None, ""):
        return None
    return str(value)


def _payload_value(record: dict[str, Any], field: str) -> Any:
    value = record.get(field)
    if value is not None:
        return value
    score = record.get("score")
    if isinstance(score, dict):
        value = score.get(field)
        if value is not None:
            return value
        for nested_key in ("stage_summary", "sleep_needed"):
            nested = score.get(nested_key)
            if isinstance(nested, dict) and nested.get(field) is not None:
                return nested[field]
    return None


def normalize_whoop_bundle(bundle: dict[str, Any]) -> NormalizedWhoopBundle:
    if not isinstance(bundle, dict):
        raise WhoopBundleError("WHOOP bundle must be a JSON object")
    if bundle.get("schema_version") != 1 or bundle.get("source") != "whoop-local":
        raise WhoopBundleError("unsupported WHOOP bundle source or schema")

    pulled_at = _timestamp(bundle.get("pulled_at"), required=True)
    assert pulled_at is not None
    window_start = _timestamp(bundle.get("window_start"))
    window_end = _timestamp(bundle.get("window_end"))
    raw_collections = bundle.get("collections")
    if not isinstance(raw_collections, dict):
        raise WhoopBundleError("collections must be an object")

    status = "complete"
    summaries: dict[str, dict[str, Any]] = {}
    observations: list[NormalizedWhoopObservation] = []

    for kind in WHOOP_KINDS:
        collection = raw_collections.get(kind)
        if not isinstance(collection, dict):
            summaries[kind] = {"status": "missing", "count": 0, "stored": 0, "skipped": 0}
            status = "partial"
            continue

        privacy_mode = collection.get("privacy_mode")
        if privacy_mode == "raw":
            raise WhoopBundleError("raw WHOOP responses are not accepted")
        if privacy_mode not in {"structured", "summary"}:
            raise WhoopBundleError(f"unsupported privacy_mode for {kind}")

        records = collection.get("records", [])
        if kind == "body_measurement" and not records and isinstance(collection.get("data"), dict):
            records = [collection["data"]]
        if not isinstance(records, list):
            raise WhoopBundleError(f"records for {kind} must be a list")

        skipped = 0
        stored = 0
        for record in records:
            if not isinstance(record, dict):
                skipped += 1
                continue
            external_id = _external_id(kind, record)
            if external_id is None:
                skipped += 1
                continue
            try:
                start_ts = _timestamp(record.get("start"))
                end_ts = _timestamp(record.get("end"))
                source_updated_at = _timestamp(record.get("updated_at"))
            except WhoopBundleError:
                skipped += 1
                continue
            payload = {
                field: value
                for field in _PAYLOAD_FIELDS[kind]
                for value in [_payload_value(record, field)]
                if value is not None
            }
            score_state = record.get("score_state")
            observations.append(NormalizedWhoopObservation(
                kind=kind,
                external_id=external_id,
                start_ts=start_ts,
                end_ts=end_ts,
                score_state=str(score_state) if score_state is not None else None,
                payload=payload,
                source_updated_at=source_updated_at,
            ))
            stored += 1

        has_more = bool(collection.get("has_more"))
        collection_error = collection.get("error")
        collection_status = "partial" if has_more or skipped or collection_error else "complete"
        if collection_status == "partial":
            status = "partial"
        summaries[kind] = {
            "status": collection_status,
            "count": int(collection.get("count", len(records)) or 0),
            "stored": stored,
            "skipped": skipped,
            "pages_fetched": int(collection.get("pages_fetched", 0) or 0),
            "has_more": has_more,
        }
        if collection_error:
            summaries[kind]["error"] = str(collection_error)[:500]

    return NormalizedWhoopBundle(
        pulled_at=pulled_at,
        window_start=window_start,
        window_end=window_end,
        status=status,
        collections=summaries,
        observations=tuple(observations),
    )


async def persist_whoop_bundle(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    bundle: dict[str, Any],
) -> tuple[WhoopSyncRun, NormalizedWhoopBundle]:
    normalized = normalize_whoop_bundle(bundle)
    run = WhoopSyncRun(
        user_id=user_id,
        pulled_at=normalized.pulled_at,
        window_start=normalized.window_start,
        window_end=normalized.window_end,
        status=normalized.status,
        collections=normalized.collections,
    )
    db.add(run)

    for item in normalized.observations:
        statement = insert(WhoopObservation).values(
            user_id=user_id,
            kind=item.kind,
            external_id=item.external_id,
            start_ts=item.start_ts,
            end_ts=item.end_ts,
            score_state=item.score_state,
            payload=item.payload,
            source_updated_at=item.source_updated_at,
            pulled_at=normalized.pulled_at,
        ).on_conflict_do_update(
            index_elements=["user_id", "kind", "external_id"],
            set_={
                "start_ts": item.start_ts,
                "end_ts": item.end_ts,
                "score_state": item.score_state,
                "payload": item.payload,
                "source_updated_at": item.source_updated_at,
                "pulled_at": normalized.pulled_at,
            },
        )
        await db.execute(statement)

    await db.commit()
    await db.refresh(run)
    return run, normalized
