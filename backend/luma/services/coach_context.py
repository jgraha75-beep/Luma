"""Build and cache a structured user context blob + rolling case file for the coach agent."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from luma.services.units import UnitSystem, fmt_weight, fmt_weight_trend

logger = logging.getLogger(__name__)

# Case file LLM prompt — kept tight to produce a bounded output
_CASE_FILE_SYSTEM = (
    "You are a health coach's clinical note-taker. "
    "You will receive the coach's existing case notes and a transcript of recent conversations. "
    "Produce updated case notes that incorporate new information. "
    "Rules: max 350 words; use short bullet points grouped under these headings only: "
    "Goals, Patterns Identified, Conclusions & Plans, Open Questions. "
    "Drop outdated or superseded points. Never include dates — just facts and decisions. "
    "Output plain text only, no markdown headers."
)

_CASE_FILE_EMPTY_NOTE = "(No prior conversations.)"


async def get_coach_context(user_id: str, db: AsyncSession) -> dict:
    """Return the cached context blob, refreshing if stale (>2h)."""
    row = await db.execute(
        text("SELECT context, updated_at FROM coach_context WHERE user_id = :uid"),
        {"uid": user_id},
    )
    cached = row.fetchone()

    if cached:
        age_hours = (datetime.now(UTC) - cached.updated_at).total_seconds() / 3600
        if age_hours < 2:
            return cached.context

    fresh = await _build_context(user_id, db)
    await _upsert_context(user_id, fresh, db)
    await db.commit()
    return fresh


async def get_case_file(user_id: str, db: AsyncSession) -> str:
    """Return the current rolling case file text (may be empty)."""
    row = await db.execute(
        text("SELECT case_file FROM coach_context WHERE user_id = :uid"),
        {"uid": user_id},
    )
    r = row.fetchone()
    if r and r.case_file:
        return r.case_file
    return ""


async def refresh_coach_context(user_id: str, db: AsyncSession) -> None:
    """Force-refresh the structured context blob (called by worker)."""
    fresh = await _build_context(user_id, db)
    await _upsert_context(user_id, fresh, db)
    await db.commit()


async def get_measurement_system(user_id: str, db: AsyncSession) -> UnitSystem:
    """Return the user's preferred unit system, defaulting to metric."""
    row = await db.execute(
        text("""
            SELECT value FROM preferences
            WHERE user_id = :uid AND kind = 'measurement_system'
              AND value IN ('metric', 'imperial')
        """),
        {"uid": user_id},
    )
    result = row.scalar_one_or_none()
    if result == "imperial":
        return "imperial"
    return "metric"


async def update_case_file(user_id: str, db: AsyncSession) -> None:
    """
    Pull any coach messages newer than case_file_updated_at, run them through
    the LLM summarizer, and persist the updated case file.

    Called by the worker every 2 hours and on new-thread creation.
    """
    # Fetch current case file and the watermark
    row = await db.execute(
        text("SELECT case_file, case_file_updated_at FROM coach_context WHERE user_id = :uid"),
        {"uid": user_id},
    )
    cached = row.fetchone()
    existing_notes = (cached.case_file if cached and cached.case_file else _CASE_FILE_EMPTY_NOTE)
    watermark = cached.case_file_updated_at if cached else None

    # Fetch new non-summary user/assistant messages since the watermark
    if watermark:
        new_rows = await db.execute(
            text("""
                SELECT cm.role, cm.content, cm.created_at, ct.title
                FROM coach_messages cm
                JOIN coach_threads ct ON ct.id = cm.thread_id
                WHERE ct.user_id = :uid
                  AND cm.is_summary = FALSE
                  AND cm.role IN ('user', 'assistant')
                  AND cm.created_at > :watermark
                ORDER BY cm.created_at
                LIMIT 200
            """),
            {"uid": user_id, "watermark": watermark},
        )
    else:
        new_rows = await db.execute(
            text("""
                SELECT cm.role, cm.content, cm.created_at, ct.title
                FROM coach_messages cm
                JOIN coach_threads ct ON ct.id = cm.thread_id
                WHERE ct.user_id = :uid
                  AND cm.is_summary = FALSE
                  AND cm.role IN ('user', 'assistant')
                ORDER BY cm.created_at
                LIMIT 200
            """),
            {"uid": user_id},
        )

    messages = new_rows.fetchall()
    if not messages:
        logger.debug("No new messages for case file update, user %s", user_id)
        return

    # Format the transcript
    transcript = "\n\n".join(
        f"[{m.role.upper()}]: {m.content[:600]}"  # cap each message to avoid blowout
        for m in messages
    )

    # Call the LLM to update the case file
    from luma.config import settings
    from luma.services.llm_client import call_llm

    try:
        resp = await call_llm(
            primary_model=settings.coach_model,
            fallback_model=settings.coach_fallback_model,
            trigger="coach_context",
            messages=[
                {"role": "system", "content": _CASE_FILE_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"## Existing case notes\n{existing_notes}\n\n"
                        f"## New conversation transcript\n{transcript}\n\n"
                        "Update the case notes."
                    ),
                },
            ],
            temperature=0.2,
            timeout=45.0,
        )
        updated_notes = resp["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.exception("Case file LLM call failed for user %s", user_id)
        return

    # Persist — upsert ensures coach_context row exists first
    await db.execute(
        text("""
            INSERT INTO coach_context (user_id, context, case_file, case_file_updated_at, updated_at)
            VALUES (:uid, '{}'::jsonb, :notes, now(), now())
            ON CONFLICT (user_id) DO UPDATE
            SET case_file = EXCLUDED.case_file,
                case_file_updated_at = EXCLUDED.case_file_updated_at
        """),
        {"uid": user_id, "notes": updated_notes},
    )
    await db.commit()
    logger.info(
        "Case file updated for user %s (%d new messages, %d chars)",
        user_id, len(messages), len(updated_notes),
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _upsert_context(user_id: str, ctx: dict, db: AsyncSession) -> None:
    await db.execute(
        text("""
            INSERT INTO coach_context (user_id, context, updated_at)
            VALUES (:uid, CAST(:ctx AS jsonb), now())
            ON CONFLICT (user_id) DO UPDATE
            SET context = EXCLUDED.context, updated_at = now()
        """),
        {"uid": user_id, "ctx": json.dumps(ctx)},
    )


async def _build_context(user_id: str, db: AsyncSession) -> dict:
    ctx: dict = {}

    # Nutrition focus is a user preference, not a clinical goal. Keep it in the
    # coach context so the agent can emphasize what this person asked to track
    # without inventing targets for informational metrics.
    focus_row = await db.execute(
        text("SELECT value FROM preferences WHERE user_id = :uid AND kind = 'nutrition_focus'"),
        {"uid": user_id},
    )
    from luma.services.nutrition_focus import METRIC_BY_ID, focus_from_preference
    focus = focus_from_preference(focus_row.scalar_one_or_none())
    ctx["nutrition_focus"] = {
        "preset": focus.preset,
        "metrics": [METRIC_BY_ID[metric_id].model_dump() for metric_id in focus.metrics],
    }

    # Demographic profile — used by meal planner + coach for personalised recommendations
    from datetime import date
    profile_row = await db.execute(
        text("""
            SELECT birth_year, biological_sex, height_cm, activity_level
            FROM users WHERE id = :uid
        """),
        {"uid": user_id},
    )
    p = profile_row.fetchone()
    if p and any([p.birth_year, p.biological_sex, p.height_cm, p.activity_level]):
        age = date.today().year - p.birth_year if p.birth_year else None
        ctx["profile"] = {
            "age": age,
            "biological_sex": p.biological_sex,
            "height_cm": float(p.height_cm) if p.height_cm else None,
            "activity_level": p.activity_level,
        }

    # Goals
    goals_row = await db.execute(
        text("""
            SELECT target_weight_kg, target_ldl_mg_dl, daily_calorie_target,
                   daily_sat_fat_g_max, daily_soluble_fiber_g, daily_protein_g_min,
                   dietary_pattern
            FROM goals WHERE user_id = :uid
        """),
        {"uid": user_id},
    )
    g = goals_row.fetchone()
    if g:
        ctx["goals"] = {
            "target_weight_kg": float(g.target_weight_kg) if g.target_weight_kg else None,
            "target_ldl_mg_dl": g.target_ldl_mg_dl,
            "daily_calorie_target": g.daily_calorie_target,
            "daily_sat_fat_g_max": float(g.daily_sat_fat_g_max) if g.daily_sat_fat_g_max else None,
            "daily_soluble_fiber_g": float(g.daily_soluble_fiber_g) if g.daily_soluble_fiber_g else None,
            "daily_protein_g_min": float(g.daily_protein_g_min) if g.daily_protein_g_min else None,
            "dietary_pattern": g.dietary_pattern,
        }

    # 7-day nutrition averages
    nutr_row = await db.execute(
        text("""
            SELECT
                AVG((nutrition->>'calories')::float) AS calories,
                AVG((nutrition->>'protein_g')::float) AS protein_g,
                AVG((nutrition->>'carbohydrates_g')::float) AS carbohydrates_g,
                AVG((nutrition->>'fat_g')::float) AS fat_g,
                AVG((nutrition->>'saturated_fat_g')::float) AS saturated_fat_g,
                AVG((nutrition->>'soluble_fiber_g')::float) AS soluble_fiber_g,
                AVG((nutrition->>'sodium_mg')::float) AS sodium_mg,
                AVG((nutrition->>'sugars_g')::float) AS sugars_g,
                AVG((nutrition->>'added_sugars_g')::float) AS added_sugars_g,
                AVG((nutrition->>'cholesterol_mg')::float) AS cholesterol_mg
            FROM meal_events
            WHERE user_id = :uid AND ts >= now() - INTERVAL '7 days'
        """),
        {"uid": user_id},
    )
    nr = nutr_row.fetchone()
    if nr and nr.calories is not None:
        ctx["nutrition_7d_avg"] = {
            key: round(getattr(nr, key), 0 if key == "calories" else 1)
            if getattr(nr, key) is not None else None
            for key in (
                "calories", "protein_g", "carbohydrates_g", "fat_g", "saturated_fat_g",
                "soluble_fiber_g", "sodium_mg", "sugars_g", "added_sugars_g", "cholesterol_mg",
            )
        }

    # Latest biometrics
    bio_row = await db.execute(
        text("""
            SELECT DISTINCT ON (metric) metric, value
            FROM biometrics
            WHERE user_id = :uid
              AND metric IN ('weight_kg','hrv_ms','rhr_bpm','sleep_score','sleep_duration_min')
            ORDER BY metric, ts DESC
        """),
        {"uid": user_id},
    )
    bio = {r.metric: round(r.value, 1) for r in bio_row}
    if bio:
        ctx["biometrics_latest"] = bio

    # Weight trend (28d slope → kg/week)
    slope_row = await db.execute(
        text("""
            SELECT regr_slope(last_value, extract(epoch from day)) * 86400 * 7 AS slope
            FROM biometrics_daily
            WHERE user_id = :uid AND metric = 'weight_kg' AND day >= now() - INTERVAL '28 days'
        """),
        {"uid": user_id},
    )
    sr = slope_row.fetchone()
    if sr and sr.slope is not None:
        ctx["weight_trend_kg_per_week"] = round(sr.slope, 3)

    # Logging consistency — distinct calendar days in SERVER_TIMEZONE so the
    # count matches the user's local days rather than UTC days.
    from luma.config import settings
    streak_row = await db.execute(
        text("""
            SELECT COUNT(DISTINCT DATE(ts AT TIME ZONE :tz)) AS days
            FROM meal_events WHERE user_id = :uid AND ts >= now() - INTERVAL '30 days'
        """),
        {"uid": user_id, "tz": settings.server_timezone},
    )
    sr2 = streak_row.fetchone()
    if sr2:
        ctx["recent_logging_days_30d"] = sr2.days

    # Last 3 alerts
    alert_rows = await db.execute(
        text("""
            SELECT rule_id, severity, narrative, ts
            FROM alerts
            WHERE user_id = :uid AND narrative IS NOT NULL
            ORDER BY ts DESC LIMIT 3
        """),
        {"uid": user_id},
    )
    alerts = []
    for r in alert_rows:
        try:
            narr = json.loads(r.narrative) if isinstance(r.narrative, str) else (r.narrative or {})
        except (TypeError, json.JSONDecodeError):
            narr = {}
        alerts.append({
            "rule_id": r.rule_id,
            "severity": r.severity,
            "headline": narr.get("headline", ""),
            "ts": r.ts.isoformat(),
        })
    if alerts:
        ctx["recent_alerts"] = alerts

    return ctx


def format_context_for_prompt(
    ctx: dict,
    case_file: str = "",
    query: str = "",
    unit_system: UnitSystem = "metric",
) -> str:
    """Render context blob + case file as a system prompt addendum.

    Values are converted to the user's preferred unit system so the LLM
    responds in matching units. Metric storage is never mutated here.
    """
    query_lower = query.lower() if query else ""

    # Determine relevance flags
    show_nutrition = not query_lower or any(w in query_lower for w in ["diet", "fiber", "fat", "calor", "protein", "eat", "food", "meal", "breakfast", "lunch", "dinner", "snack", "nutrition", "sat", "carb", "sugar"])
    show_biometrics = not query_lower or any(w in query_lower for w in ["weight", "kg", "lb", "pound", "scale", "hrv", "rhr", "sleep", "heart", "pulse", "bpm", "ms", "fit", "health", "biometric"])
    show_alerts = not query_lower or any(w in query_lower for w in ["alert", "insight", "narrat", "notification", "warning"])

    lines = ["## User snapshot (auto-updated every 2 hours)"]

    if unit_system == "imperial":
        lines.append("**Unit preference:** imperial — always respond using lbs and ft/in for body measurements")

    if goals := ctx.get("goals"):
        parts = []
        if goals.get("daily_calorie_target"):
            parts.append(f"{goals['daily_calorie_target']} kcal/day target")
        if goals.get("daily_sat_fat_g_max"):
            parts.append(f"sat fat ≤{goals['daily_sat_fat_g_max']}g")
        if goals.get("daily_soluble_fiber_g"):
            parts.append(f"fiber ≥{goals['daily_soluble_fiber_g']}g")
        if goals.get("target_weight_kg"):
            parts.append(f"goal weight {fmt_weight(goals['target_weight_kg'], unit_system)}")
        if goals.get("dietary_pattern"):
            parts.append(goals["dietary_pattern"])
        if parts:
            lines.append("**Goals:** " + ", ".join(parts))

    if show_nutrition:
        if focus := ctx.get("nutrition_focus"):
            labels = ", ".join(metric["label"] for metric in focus["metrics"])
            lines.append(f"**Nutrition focus ({focus['preset']}):** {labels}")
        if nutr := ctx.get("nutrition_7d_avg"):
            labels = {
                "calories": ("kcal", 0),
                "protein_g": ("g protein", 1),
                "carbohydrates_g": ("g carbs", 1),
                "fat_g": ("g fat", 1),
                "saturated_fat_g": ("g sat fat", 1),
                "soluble_fiber_g": ("g soluble fiber", 1),
                "sodium_mg": ("mg sodium", 0),
                "sugars_g": ("g sugar", 1),
                "added_sugars_g": ("g added sugar", 1),
                "cholesterol_mg": ("mg cholesterol", 0),
            }
            focus_ids = {metric["id"] for metric in (focus or {}).get("metrics", [])}
            parts = []
            for key, (unit, digits) in labels.items():
                if key in focus_ids and nutr.get(key) is not None:
                    value = int(nutr[key]) if digits == 0 else nutr[key]
                    parts.append(f"{value} {unit} avg")
            if parts:
                lines.append("**Last 7d nutrition:** " + ", ".join(parts))

    if show_biometrics:
        if bio := ctx.get("biometrics_latest"):
            parts = []
            if bio.get("weight_kg"):
                parts.append(f"weight {fmt_weight(bio['weight_kg'], unit_system)}")
            if bio.get("hrv_ms"):
                parts.append(f"HRV {bio['hrv_ms']} ms")
            if bio.get("sleep_score"):
                parts.append(f"sleep score {bio['sleep_score']}")
            if parts:
                lines.append("**Latest biometrics:** " + ", ".join(parts))

        if (slope := ctx.get("weight_trend_kg_per_week")) is not None:
            direction = "↓" if slope < 0 else "↑" if slope > 0 else "→"
            trend_str = fmt_weight_trend(slope, unit_system)
            lines.append(f"**Weight trend (28d):** {direction} {trend_str}")

    if ctx.get("recent_logging_days_30d") is not None:
        lines.append(f"**Logging consistency:** {ctx['recent_logging_days_30d']}/30 days logged")

    if show_alerts:
        if alerts := ctx.get("recent_alerts"):
            lines.append("**Recent alerts:** " + "; ".join(
                f"[{a['severity']}] {a['headline']}" for a in alerts
            ))

    # Rolling case file — injected as a separate section
    if case_file and case_file != _CASE_FILE_EMPTY_NOTE:
        lines.append("\n## Coaching history (rolling summary)")
        lines.append(case_file)

    return "\n".join(lines)
