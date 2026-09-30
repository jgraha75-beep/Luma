"""Regression contract for deleting a generated weekly meal plan."""

from luma.main import app


def test_plan_delete_route_is_registered():
    """The plan screen needs a user-scoped delete endpoint, not only archive-on-regenerate."""
    path = app.openapi()["paths"].get("/api/v1/plan/{plan_id}", {})
    assert "delete" in path

