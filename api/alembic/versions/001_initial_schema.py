"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from geoalchemy2 import Geography

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

FUEL_ENUM = ENUM("gazole", "sp95", "sp98", "e10", "e85", "gplc", name="fuel_type", create_type=False)
OUTAGE_ENUM = ENUM("none", "temporary", "definitive", name="outage_type", create_type=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE TYPE fuel_type AS ENUM ('gazole', 'sp95', 'sp98', 'e10', 'e85', 'gplc')")
    op.execute("CREATE TYPE outage_type AS ENUM ('none', 'temporary', 'definitive')")

    op.create_table(
        "stations",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("address", sa.Text),
        sa.Column("postal_code", sa.Text),
        sa.Column("city", sa.Text),
        sa.Column("dept_code", sa.Text),
        sa.Column("dept_name", sa.Text),
        sa.Column("region_name", sa.Text),
        sa.Column("road_type", sa.Text),
        sa.Column("geom", Geography("POINT", srid=4326), nullable=False),
        sa.Column("services", JSONB),
        sa.Column("opening_hours", JSONB),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("stations_geom_gix", "stations", ["geom"], postgresql_using="gist")

    op.create_table(
        "station_prices",
        sa.Column("station_id", sa.BigInteger, sa.ForeignKey("stations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fuel", FUEL_ENUM, nullable=False),
        sa.Column("price_eur", sa.Numeric(5, 3)),
        sa.Column("price_maj", sa.TIMESTAMP(timezone=True)),
        sa.Column("outage", OUTAGE_ENUM, nullable=False, server_default="none"),
        sa.PrimaryKeyConstraint("station_id", "fuel"),
    )
    op.create_index(
        "station_prices_fuel_price_idx",
        "station_prices",
        ["fuel", "price_eur"],
        postgresql_where=sa.text("price_eur IS NOT NULL"),
    )

    op.create_table(
        "etl_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("rows_stations", sa.Integer),
        sa.Column("rows_prices", sa.Integer),
        sa.Column("source_bytes", sa.BigInteger),
        sa.Column("error", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("etl_runs")
    op.drop_index("station_prices_fuel_price_idx", table_name="station_prices")
    op.drop_table("station_prices")
    op.drop_index("stations_geom_gix", table_name="stations")
    op.drop_table("stations")
    op.execute("DROP TYPE outage_type")
    op.execute("DROP TYPE fuel_type")
