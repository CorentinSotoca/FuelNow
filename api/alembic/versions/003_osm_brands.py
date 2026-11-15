"""osm_fuel_pois + station_brands (enseignes OpenStreetMap)

Revision ID: 003
Revises: 002
Create Date: 2026-11-15
"""
import sqlalchemy as sa
from geoalchemy2 import Geography

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Cache des stations-service OSM (Overpass), remplacé intégralement à
    # chaque refresh (hebdomadaire). station_ref = tag ref:FR:prix-carburants
    # (id du point de vente du flux officiel) ; NULL si le POI n'est pas
    # référencé — il reste alors candidat au match par proximité.
    op.create_table(
        "osm_fuel_pois",
        sa.Column("osm_type", sa.Text, nullable=False),
        sa.Column("osm_id", sa.BigInteger, nullable=False),
        sa.Column("station_ref", sa.BigInteger),
        sa.Column("brand", sa.Text),
        sa.Column("osm_name", sa.Text),
        sa.Column("geom", Geography("POINT", srid=4326), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("osm_fuel_pois_station_ref_idx", "osm_fuel_pois", ["station_ref"])
    op.create_index("osm_fuel_pois_geom_gix", "osm_fuel_pois", ["geom"], postgresql_using="gist")

    # Enseigne par station : match exact par ref:FR:prix-carburants, sinon POI
    # OSM le plus proche à moins de 150 m. Une ligne par station au plus.
    # La table est vidée et reconstruite à chaque run ETL FR (même transaction
    # que le remplacement des stations) — d'où le TRUNCATE listé dans load.py.
    op.create_table(
        "station_brands",
        sa.Column("station_id", sa.BigInteger, sa.ForeignKey("stations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand", sa.Text),
        sa.Column("osm_name", sa.Text),
        sa.Column("match_type", sa.Text, nullable=False),
        sa.Column("matched_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("station_id"),
    )


def downgrade() -> None:
    op.drop_table("station_brands")
    op.drop_index("osm_fuel_pois_geom_gix", table_name="osm_fuel_pois")
    op.drop_index("osm_fuel_pois_station_ref_idx", table_name="osm_fuel_pois")
    op.drop_table("osm_fuel_pois")
