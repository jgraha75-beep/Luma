"""preserve serving-based nutrition provenance in favorites

Revision ID: 0035_fav_serving_basis
Revises: 0034_add_whoop_observations
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0035_fav_serving_basis"
down_revision: str | None = "0034_add_whoop_observations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "favorite_items",
        sa.Column("nutrition_basis", sa.Text(), nullable=False, server_default="per_100g"),
    )
    op.add_column("favorite_items", sa.Column("serving_count", sa.Float(), nullable=True))
    op.add_column(
        "favorite_items",
        sa.Column("nutrients_per_serving", postgresql.JSONB(), nullable=True),
    )
    op.add_column("favorite_items", sa.Column("nutrient_source", sa.Text(), nullable=True))
    op.add_column("favorite_items", sa.Column("source_id", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_favorite_items_nutrition_basis",
        "favorite_items",
        "nutrition_basis IN ('per_100g', 'per_serving')",
    )
    op.create_check_constraint(
        "ck_favorite_items_serving_count_positive",
        "favorite_items",
        "serving_count IS NULL OR serving_count > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_favorite_items_serving_count_positive", "favorite_items", type_="check")
    op.drop_constraint("ck_favorite_items_nutrition_basis", "favorite_items", type_="check")
    op.drop_column("favorite_items", "source_id")
    op.drop_column("favorite_items", "nutrient_source")
    op.drop_column("favorite_items", "nutrients_per_serving")
    op.drop_column("favorite_items", "serving_count")
    op.drop_column("favorite_items", "nutrition_basis")
