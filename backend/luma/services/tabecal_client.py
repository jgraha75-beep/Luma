"""Tabecal client for Japanese chain-menu nutrition data.

Tabecal values are published for a menu item/size, not normalized to 100 g.
The adapter keeps that basis explicit so callers do not accidentally treat a
restaurant serving as a gram-based food.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping

import httpx

from luma.config import settings

logger = logging.getLogger("tabecal_client")


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_item(item: Mapping[str, object]) -> dict[str, object]:
    """Map a Tabecal item into Luma's provider-neutral serving shape."""
    name = str(item.get("name") or "Unnamed menu item").strip()
    size = str(item.get("size") or "").strip()
    display_name = f"{name}（{size}）" if size else name

    nutrients: dict[str, float | None] = {
        "calories": _number(item.get("kcal")),
        "protein_g": _number(item.get("protein_g")),
        "fat_g": _number(item.get("fat_g")),
        "saturated_fat_g": _number(item.get("saturated_fat_g")),
        "carbohydrates_g": _number(item.get("carb_g")),
        "sugars_g": _number(item.get("sugar_g")),
        "fiber_g": _number(item.get("fiber_g")),
        "sodium_mg": _number(item.get("sodium_mg")),
    }

    metadata: dict[str, object] = {
        "chain_slug": item.get("chain_slug"),
        "genre": item.get("genre"),
        "category": item.get("category"),
        "salt_g": _number(item.get("salt_g")),
        "price_jpy": _number(item.get("price")),
        "valid_from": item.get("valid_from"),
    }

    return {
        "source": "tabecal",
        "source_id": f"tabecal_{item.get('item_key') or display_name}",
        "name": display_name,
        "brand": str(item.get("chain") or "").strip() or None,
        "serving_size_g": _number(item.get("weight_g")),
        "nutrition_basis": "per_serving",
        "nutrients": nutrients,
        "metadata": metadata,
    }


async def search_items(query: str, *, limit: int = 20, offset: int = 0) -> list[dict[str, object]]:
    """Search Tabecal's Japanese menu catalog.

    The API supports anonymous requests, with an optional key for higher
    limits. Failures are intentionally non-fatal so USDA/OFF remain available.
    """
    params = {"q": query, "limit": limit, "offset": offset}
    headers = {"User-Agent": "LumaHealthTracker/1.0"}
    if settings.tabecal_api_key:
        headers["X-Api-Key"] = settings.tabecal_api_key

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.tabecal_api_base.rstrip('/')}/items",
                params=params,
                headers=headers,
            )
            if response.status_code != 200:
                logger.warning("Tabecal returned status %s", response.status_code)
                return []
            payload = response.json()
    except Exception:
        logger.exception("Tabecal search failed")
        return []

    raw_items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        return []
    return [normalize_item(item) for item in raw_items if isinstance(item, Mapping)]

