from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, Numeric, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from geoalchemy2 import Geography
from datetime import datetime

FUEL_TYPES = ("gazole", "sp95", "sp98", "e10", "e85", "gplc")
OUTAGE_TYPES = ("none", "temporary", "definitive")


class Base(DeclarativeBase):
    pass


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    address: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    dept_code: Mapped[str | None] = mapped_column(Text)
    dept_name: Mapped[str | None] = mapped_column(Text)
    region_name: Mapped[str | None] = mapped_column(Text)
    road_type: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[Geography] = mapped_column(Geography("POINT", srid=4326), nullable=False)
    services: Mapped[dict | None] = mapped_column(JSONB)
    opening_hours: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class StationPrice(Base):
    __tablename__ = "station_prices"

    station_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stations.id", ondelete="CASCADE"), primary_key=True)
    fuel: Mapped[str] = mapped_column(Enum(*FUEL_TYPES, name="fuel_type"), primary_key=True)
    price_eur: Mapped[float | None] = mapped_column(Numeric(5, 3))
    price_maj: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    outage: Mapped[str] = mapped_column(Enum(*OUTAGE_TYPES, name="outage_type"), nullable=False, server_default="none")


class EtlRun(Base):
    __tablename__ = "etl_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    rows_stations: Mapped[int | None] = mapped_column(Integer)
    rows_prices: Mapped[int | None] = mapped_column(Integer)
    source_bytes: Mapped[int | None] = mapped_column(BigInteger)
    error: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="fr")
