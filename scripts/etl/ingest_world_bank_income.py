"""Ingest World Bank country income classification.

Source: https://api.worldbank.org/v2/country?format=json&per_page=400
Official, machine-readable, no scraping, no login. This is the
authoritative source the APC-waiver country tiers (Research4Life
Group A/full-waiver vs Group B/50%-discount, mirrored independently by
Elsevier/Wiley/Sage/OUP's own stated policies) are actually keyed to.
"""
from __future__ import annotations

import datetime

import requests

from common import etl_run
from src.db.engine import session_scope
from src.db.models import CountryIncomeClassification

URL = "https://api.worldbank.org/v2/country?format=json&per_page=400"

_INCOME_MAP = {
    "Low income": "low",
    "Lower middle income": "lower_middle",
    "Upper middle income": "upper_middle",
    "High income": "high",
}


def _fetch_countries():
    resp = requests.get(URL, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if len(payload) < 2:
        return []
    return payload[1]


def run():
    countries = _fetch_countries()
    now = datetime.datetime.utcnow()

    with etl_run("world_bank_income") as counters:
        with session_scope() as session:
            for entry in countries:
                counters.fetched += 1
                income_level = (entry.get("incomeLevel") or {}).get("value", "")
                income_group = _INCOME_MAP.get(income_level)
                iso3 = entry.get("id", "")
                if not income_group or not iso3 or len(iso3) != 3:
                    counters.failed += 1
                    continue
                row = session.query(CountryIncomeClassification).filter_by(country_code=iso3).one_or_none()
                if row is None:
                    row = CountryIncomeClassification(country_code=iso3)
                    session.add(row)
                row.country_name = entry.get("name", "")
                row.income_group = income_group
                row.source = "World Bank API"
                row.updated_at = now
                counters.upserted += 1


if __name__ == "__main__":
    run()
