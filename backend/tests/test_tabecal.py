from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient


SAMPLE_ITEM = {
    "item_key": "5a1c0e9d2b7f4a10",
    "chain": "吉野家",
    "chain_slug": "yoshinoya",
    "genre": "gyudon",
    "name": "牛丼",
    "size": "並盛",
    "category": "牛丼",
    "kcal": 635.0,
    "protein_g": 20.0,
    "fat_g": 23.4,
    "carb_g": 89.0,
    "fiber_g": None,
    "sugar_g": None,
    "salt_g": 2.7,
    "sodium_mg": None,
    "weight_g": None,
    "price": 650,
    "valid_from": "2026-08-16",
}


def _make_fake_user():
    user = MagicMock()
    user.id = uuid4()
    return user


def test_normalize_item_preserves_serving_basis_and_unknowns():
    from luma.services.tabecal_client import normalize_item

    out = normalize_item(SAMPLE_ITEM)

    assert out["source"] == "tabecal"
    assert out["source_id"] == "tabecal_5a1c0e9d2b7f4a10"
    assert out["name"] == "牛丼（並盛）"
    assert out["brand"] == "吉野家"
    assert out["nutrition_basis"] == "per_serving"
    assert out["serving_size_g"] is None
    assert out["nutrients"]["calories"] == 635.0
    assert out["nutrients"]["protein_g"] == 20.0
    assert out["nutrients"]["sodium_mg"] is None
    assert out["metadata"]["salt_g"] == 2.7


def test_japan_search_returns_tabecal_nutrition_items():
    fake_user = _make_fake_user()
    from luma.api.foods import router
    from luma.deps import get_current_user, get_db

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/foods")

    async def _mock_db():
        yield AsyncMock()

    async def _mock_user():
        return fake_user

    app.dependency_overrides[get_db] = _mock_db
    app.dependency_overrides[get_current_user] = _mock_user

    with patch(
        "luma.api.foods.tabecal_client.search_items",
        new=AsyncMock(return_value=[SAMPLE_ITEM]),
    ) as search:
        with TestClient(app) as client:
            response = client.get("/api/v1/foods/japan/search?q=牛丼")

    assert response.status_code == 200
    assert response.json() == [
        {
            "source": "tabecal",
            "source_id": "tabecal_5a1c0e9d2b7f4a10",
            "name": "牛丼（並盛）",
            "brand": "吉野家",
            "serving_size_g": None,
            "nutrition_basis": "per_serving",
            "nutrients": {
                "calories": 635.0,
                "protein_g": 20.0,
                "fat_g": 23.4,
                "saturated_fat_g": None,
                "carbohydrates_g": 89.0,
                "sugars_g": None,
                "fiber_g": None,
                "sodium_mg": None,
            },
            "metadata": {
                "chain_slug": "yoshinoya",
                "genre": "gyudon",
                "category": "牛丼",
                "salt_g": 2.7,
                "price_jpy": 650.0,
                "valid_from": "2026-08-16",
            },
        }
    ]
    search.assert_awaited_once_with("牛丼", limit=20, offset=0)

