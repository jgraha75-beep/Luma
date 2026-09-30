from types import SimpleNamespace


def test_favorite_item_accepts_serving_based_provenance():
    from luma.api.favorites import FavoriteItemIn

    item = FavoriteItemIn(
        food_name="牛丼（並盛）",
        brand="吉野家",
        quantity_g=100,
        nutrients={"calories": 635, "protein_g": 20},
        nutrition_basis="per_serving",
        serving_count=1.5,
        nutrients_per_serving={"calories": 635, "protein_g": 20},
        nutrient_source="tabecal",
        source_id="tabecal_yoshinoya_regular",
    )

    assert item.nutrition_basis == "per_serving"
    assert item.serving_count == 1.5
    assert item.nutrients_per_serving["calories"] == 635
    assert item.nutrient_source == "tabecal"


def test_favorite_item_response_defaults_legacy_rows_to_per_100g():
    from luma.api.favorites import _item_row_to_dict

    row = SimpleNamespace(
        item_id=None,
        sort_order=0,
        food_name="Oats",
        brand=None,
        quantity_g=40,
        nutrients={"calories": 150},
        nutrition_basis=None,
        serving_count=None,
        nutrients_per_serving=None,
        nutrient_source=None,
        source_id=None,
    )

    out = _item_row_to_dict(row)
    assert out["nutrition_basis"] == "per_100g"
    assert out["serving_count"] is None
    assert out["nutrients_per_serving"] is None
