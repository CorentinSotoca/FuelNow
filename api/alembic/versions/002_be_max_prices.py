"""be_max_prices table + etl_runs.source column

Revision ID: 002
Revises: 001
Create Date: 2026-08-28
"""
import sqlalchemy as sa

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "be_max_prices",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("fuel_code", sa.Text, nullable=False),
        sa.Column("product_label", sa.Text, nullable=False),
        sa.Column("price_eur", sa.Numeric(5, 4), nullable=False),
        sa.Column("price_date", sa.Date, nullable=False),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("fuel_code", "price_date", name="be_max_prices_fuel_date_uc"),
    )
    op.create_index(
        "be_max_prices_fuel_date_idx",
        "be_max_prices",
        ["fuel_code", "price_date"],
    )

    op.add_column("etl_runs", sa.Column("source", sa.Text, nullable=False, server_default="fr"))


def downgrade() -> None:
    op.drop_column("etl_runs", "source")
    op.drop_index("be_max_prices_fuel_date_idx", table_name="be_max_prices")
    op.drop_table("be_max_prices")
