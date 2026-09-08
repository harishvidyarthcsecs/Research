"""Backfill missing journal.publisher / .country / .homepage_url from
OpenAlex - the three gaps in the canonical `journals` table that are
genuinely fixable (audited live 2026-08-18: 27% / 47% / 63% of journals
missing these respectively). Other gaps (MJL, real CiteScore, DOAJ/CFR
coverage) are structural ceilings, not touched here.

Only fills TRUE nulls - never overwrites a value CFR/DOAJ/Scopus already
supplied, since those sources are more authoritative for their own
fields than a generic OpenAlex lookup would be.

OpenAlex's free, no-login `/sources/issn:{issn}` endpoint (same one
already used for the CiteScore estimate) returns `host_organization_name`
(publisher) and `homepage_url` directly, and `country_code` as an ISO-2
code - converted to a full country name via `pycountry` so it stays
consistent with the full names CFR/DOAJ already store (e.g. "Egypt", not
"EG").
"""
from __future__ import annotations

import time

import pycountry
import requests

from common import etl_run
from src.db.engine import session_scope
from src.db.models import Journal

OPENALEX_URL = "https://api.openalex.org/sources/issn:{issn}"
_DELAY_S = 0.15
_HEADERS = {"User-Agent": "research-agent-journal-db (mailto:harishvidyarth.n.2024.csecs@rajalakshmi.edu.in)"}


def _country_name(iso2: str):
    if not iso2:
        return None
    country = pycountry.countries.get(alpha_2=iso2)
    return country.name if country else None


def _fetch_enrichment(issn: str):
    resp = requests.get(OPENALEX_URL.format(issn=issn), timeout=15, headers=_HEADERS)
    if resp.status_code != 200:
        return None
    data = resp.json() or {}
    return {
        "publisher": data.get("host_organization_name"),
        "homepage_url": data.get("homepage_url"),
        "country": _country_name(data.get("country_code")),
    }


def run(limit: int = 500):
    with etl_run("openalex_enrichment") as counters:
        with session_scope() as session:
            targets = (
                session.query(Journal)
                .filter(
                    (Journal.publisher.is_(None)) | (Journal.publisher == "")
                    | (Journal.country.is_(None)) | (Journal.country == "")
                    | (Journal.homepage_url.is_(None))
                )
                .limit(limit)
                .all()
            )
            for journal in targets:
                counters.fetched += 1
                try:
                    enrichment = _fetch_enrichment(journal.issn_l)
                except Exception:
                    counters.failed += 1
                    time.sleep(_DELAY_S)
                    continue
                time.sleep(_DELAY_S)
                if enrichment is None:
                    counters.failed += 1
                    continue

                changed = False
                if not journal.publisher and enrichment["publisher"]:
                    journal.publisher = enrichment["publisher"]
                    changed = True
                if not journal.country and enrichment["country"]:
                    journal.country = enrichment["country"]
                    changed = True
                if not journal.homepage_url and enrichment["homepage_url"]:
                    journal.homepage_url = enrichment["homepage_url"]
                    changed = True

                if changed:
                    counters.upserted += 1
                else:
                    counters.failed += 1  # OpenAlex had nothing new either - honest, not an error

                if counters.fetched % 100 == 0:
                    # Same periodic-commit reasoning as the CiteScore script -
                    # this can run for hours, don't risk one giant transaction.
                    session.commit()


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    run(limit=n)
