"""WHOOP import and read-only status for the signed-in Luma user."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from luma.db.models import WhoopObservation, WhoopSyncRun
from luma.deps import CurrentUser, DbDep
from luma.services.whoop_import import WhoopBundleError, persist_whoop_bundle

router = APIRouter()


@router.post("/whoop/import", status_code=status.HTTP_201_CREATED)
async def import_whoop_bundle(
    bundle: dict[str, Any],
    user: CurrentUser,
    db: DbDep,
) -> dict[str, Any]:
    """Import one privacy-sanitized bundle produced by the local WHOOP bridge.

    OAuth credentials never enter Luma: the host-side bridge owns that
    connection and sends only the structured bundle.  The normalizer enforces
    the schema, strips identity fields, and upserts source records so retries
    are safe.
    """
    try:
        run, normalized = await persist_whoop_bundle(db, user_id=user.id, bundle=bundle)
    except WhoopBundleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return {
        "sync_run_id": str(run.id),
        "status": normalized.status,
        "observations": len(normalized.observations),
        "collections": normalized.collections,
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _observation_json(item: WhoopObservation | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "external_id": item.external_id,
        "start": _iso(item.start_ts),
        "end": _iso(item.end_ts),
        "score_state": item.score_state,
        "pulled_at": _iso(item.pulled_at),
        **item.payload,
    }


@router.get("/whoop/status")
async def whoop_status(user: CurrentUser, db: DbDep) -> dict[str, Any]:
    latest_run = await db.scalar(
        select(WhoopSyncRun)
        .where(WhoopSyncRun.user_id == user.id)
        .order_by(WhoopSyncRun.pulled_at.desc())
        .limit(1)
    )

    latest: dict[str, dict[str, Any] | None] = {}
    for kind in ("recovery", "sleep", "cycle", "workout", "body_measurement"):
        item = await db.scalar(
            select(WhoopObservation)
            .where(WhoopObservation.user_id == user.id, WhoopObservation.kind == kind)
            .order_by(
                func.coalesce(
                    WhoopObservation.end_ts,
                    WhoopObservation.start_ts,
                    WhoopObservation.source_updated_at,
                    WhoopObservation.pulled_at,
                ).desc()
            )
            .limit(1)
        )
        latest[kind] = _observation_json(item)

    if latest_run is None:
        return {
            "source": "whoop",
            "separate_from_apple_health": True,
            "quality": "unknown",
            "reasons": ["WHOOP has not been synced"],
            "sync": None,
            "latest": latest,
        }

    now = datetime.now(UTC)
    stale = latest_run.pulled_at < now - timedelta(hours=24)
    reasons: list[str] = []
    if latest_run.status != "complete":
        reasons.append("The latest WHOOP pull is incomplete")
    if stale:
        reasons.append("The latest WHOOP pull is more than 24 hours old")
    quality = "partial" if latest_run.status != "complete" else "stale" if stale else "complete"

    return {
        "source": "whoop",
        "separate_from_apple_health": True,
        "quality": quality,
        "reasons": reasons,
        "sync": {
            "status": latest_run.status,
            "pulled_at": _iso(latest_run.pulled_at),
            "window_start": _iso(latest_run.window_start),
            "window_end": _iso(latest_run.window_end),
            "collections": latest_run.collections,
        },
        "latest": latest,
    }
