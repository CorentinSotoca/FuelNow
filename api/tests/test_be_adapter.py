from datetime import date

import pytest

from etl.be_adapter import StatbelAdapter, parse_be_date


SAMPLE_FACTS = [
    {"Produit": "Diesel B7 (€/L)", "Prix TVA incl.": 1.732, "Jour": "28AUG26", "Groupe de produits": "Carburants"},
    {"Produit": "Essence 95 RON E5 (€/L)", "Prix TVA incl.": 1.789, "Jour": "28AUG26", "Groupe de produits": "Carburants"},
    {"Produit": "Essence 95 RON E10 (€/L)", "Prix TVA incl.": 1.759, "Jour": "28AUG26", "Groupe de produits": "Carburants"},
    {"Produit": "Essence 98 RON E5 (€/L)", "Prix TVA incl.": 1.849, "Jour": "28AUG26", "Groupe de produits": "Carburants"},
    {"Produit": "Autogas LPG (à la pompe) (€/L)", "Prix TVA incl.": 0.852, "Jour": "28AUG26", "Groupe de produits": "Carburants"},
    {"Produit": "Some Other Product (€/L)", "Prix TVA incl.": 9.999, "Jour": "28AUG26", "Groupe de produits": "Autre"},
    {"Produit": "Diesel B7 (€/L)", "Prix TVA incl.": 1.700, "Jour": "27AUG26", "Groupe de produits": "Carburants"},
    {"Produit": "Diesel B7 (€/L)", "Prix TVA incl.": None, "Jour": "26AUG26", "Groupe de produits": "Carburants"},
    {"Produit": "Diesel B7 (€/L)", "Prix TVA incl.": 1.732, "Jour": "INVALID", "Groupe de produits": "Carburants"},
]


@pytest.fixture()
def adapter() -> StatbelAdapter:
    return StatbelAdapter(SAMPLE_FACTS)


def test_parse_be_date_valid():
    assert parse_be_date("31AUG26") == date(2026, 8, 31)
    assert parse_be_date("01JAN26") == date(2026, 1, 1)
    assert parse_be_date("15jan26") == date(2026, 1, 15)


def test_parse_be_date_invalid():
    assert parse_be_date("INVALID") is None
    assert parse_be_date("XX") is None
    assert parse_be_date("32JAN26") is None


def test_parse_filters_relevant_products(adapter: StatbelAdapter):
    records = adapter.parse()
    fuel_codes = {r.fuel_code for r in records}
    assert fuel_codes == {"gazole", "sp95", "sp98", "e10", "gplc"}


def test_parse_excludes_unmapped_products(adapter: StatbelAdapter):
    records = adapter.parse()
    assert all("Some Other Product" not in r.product_label for r in records)


def test_parse_excludes_null_price(adapter: StatbelAdapter):
    records = adapter.parse()
    gazole_dates = {(r.fuel_code, r.price_date) for r in records if r.fuel_code == "gazole"}
    assert ("gazole", date(2026, 8, 26)) not in gazole_dates


def test_parse_excludes_invalid_date(adapter: StatbelAdapter):
    records = adapter.parse()
    assert all(r.price_date is not None for r in records)


def test_parse_mapping(adapter: StatbelAdapter):
    records = adapter.parse()
    label_by_code = {r.fuel_code: r.product_label for r in records if r.price_date == date(2026, 8, 28)}
    assert label_by_code["gazole"] == "Diesel B7 (€/L)"
    assert label_by_code["sp95"] == "Essence 95 RON E5 (€/L)"
    assert label_by_code["sp98"] == "Essence 98 RON E5 (€/L)"
    assert label_by_code["e10"] == "Essence 95 RON E10 (€/L)"
    assert label_by_code["gplc"] == "Autogas LPG (à la pompe) (€/L)"


def test_parse_multiple_dates(adapter: StatbelAdapter):
    records = adapter.parse()
    gazole_records = [r for r in records if r.fuel_code == "gazole"]
    dates = {r.price_date for r in gazole_records}
    assert date(2026, 8, 28) in dates
    assert date(2026, 8, 27) in dates


def test_parse_price_values(adapter: StatbelAdapter):
    records = adapter.parse()
    gazole_28 = next(r for r in records if r.fuel_code == "gazole" and r.price_date == date(2026, 8, 28))
    assert gazole_28.price_eur == 1.732


def test_empty_facts():
    adapter = StatbelAdapter([])
    assert adapter.parse() == []
