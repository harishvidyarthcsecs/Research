"""Bulk-enrich existing journals from the OpenAlex Sources API.

This importer is deliberately enrichment-only: it matches OpenAlex sources to
the existing canonical journal set by ISSN and skips unmatched sources. Values
are written only into empty/unknown fields, so verified APCs and real Scopus
CiteScores are never overwritten.
"""
from __future__ import annotations

import argparse
import datetime
import logging
import math
import time
from typing import Any

import requests

from common import IssnIndex, etl_run
from src.db.engine import session_scope
from src.db.models import JournalAPCConsolidated, JournalScopus

OPENALEX_URL = "https://api.openalex.org/sources"
SOURCE_LABEL = "openalex_2yr_mean_citedness"
USER_AGENT = "research-agent (mailto:harishvidyarth.n.2024.csecs@rajalakshmi.edu.in)"
SELECT_FIELDS = ",".join((
    "id", "issn_l", "issn", "display_name", "host_organization_name",
    "homepage_url", "country_code", "is_oa", "is_in_doaj", "apc_usd",
    "apc_prices", "summary_stats", "works_count",
))
MAX_RETRIES = 5

logger = logging.getLogger(__name__)


def _present(value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() in {"nil", "n/a"}:
            return None
    return value


def _finite_float(value: Any) -> float | None:
    value = _present(value)
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _fetch_page(http: requests.Session, cursor: str) -> dict:
    params = {
        "filter": "type:journal",
        "per-page": 200,
        "cursor": cursor,
        "select": SELECT_FIELDS,
    }
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = http.get(OPENALEX_URL, params=params, timeout=30)
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2 ** attempt)
            continue

        if response.status_code == 429 or 500 <= response.status_code < 600:
            if attempt == MAX_RETRIES:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 2 ** attempt
            except ValueError:
                delay = 2 ** attempt
            time.sleep(max(0.0, min(delay, 60.0)))
            continue

        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("OpenAlex returned a non-object response")
        return payload

    raise RuntimeError("OpenAlex request retry loop ended unexpectedly")


def _source_issns(source: dict) -> list[str]:
    raw = [source.get("issn_l")]
    issns = source.get("issn")
    if isinstance(issns, list):
        raw.extend(issns)
    return [value for value in raw if _present(value) is not None]


def run(limit_pages: int | None = None):
    if limit_pages is not None and limit_pages < 1:
        raise ValueError("limit_pages must be at least 1")

    totals = {
        "pages": 0,
        "sources_seen": 0,
        "matched": 0,
        "homepage_set": 0,
        "citescore_set": 0,
        "apc_set": 0,
    }
    snapshot_date = datetime.datetime.utcnow()

    with etl_run("openalex_bulk") as counters:
        with session_scope() as session:
            index = IssnIndex(session)
            scopus_by_journal = {
                row.journal_id: row for row in session.query(JournalScopus).all()
            }
            apc_by_journal = {
                row.journal_id: row for row in session.query(JournalAPCConsolidated).all()
            }
            http = requests.Session()
            http.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
            cursor = "*"

            while cursor and (limit_pages is None or totals["pages"] < limit_pages):
                payload = _fetch_page(http, cursor)
                results = payload.get("results") or []
                if not isinstance(results, list):
                    raise ValueError("OpenAlex response 'results' is not a list")

                totals["pages"] += 1
                for source in results:
                    if not isinstance(source, dict):
                        counters.failed += 1
                        continue
                    totals["sources_seen"] += 1
                    counters.fetched += 1

                    journal = index.find(_source_issns(source))
                    if journal is None:
                        continue
                    totals["matched"] += 1

                    homepage = _present(source.get("homepage_url"))
                    if homepage and not _present(journal.homepage_url):
                        journal.homepage_url = homepage
                        totals["homepage_set"] += 1

                    stats = source.get("summary_stats") or {}
                    estimate = _finite_float(
                        stats.get("2yr_mean_citedness") if isinstance(stats, dict) else None
                    )
                    if estimate is not None:
                        scopus = scopus_by_journal.get(journal.id)
                        if scopus is None:
                            scopus = JournalScopus(journal_id=journal.id, snapshot_date=snapshot_date)
                            session.add(scopus)
                            scopus_by_journal[journal.id] = scopus
                        if scopus.citescore is None and scopus.citescore_estimated is None:
                            scopus.citescore_estimated = estimate
                            scopus.citescore_estimate_source = SOURCE_LABEL
                            totals["citescore_set"] += 1

                    apc_usd = _finite_float(source.get("apc_usd"))
                    if apc_usd is not None and apc_usd > 0:
                        consolidated = apc_by_journal.get(journal.id)
                        if consolidated is not None and consolidated.confidence == "unknown":
                            consolidated.apc_usd = apc_usd
                            consolidated.apc_source = "openalex"
                            consolidated.confidence = "estimated"
                            consolidated.updated_at = snapshot_date
                            totals["apc_set"] += 1

                counters.upserted = (
                    totals["homepage_set"] + totals["citescore_set"] + totals["apc_set"]
                )
                session.commit()
                cursor = (payload.get("meta") or {}).get("next_cursor")
                message = " ".join(f"{key}={value}" for key, value in totals.items())
                print(f"[openalex_bulk] {message}")
                logger.info("openalex_bulk progress: %s", message)

    message = " ".join(f"{key}={value}" for key, value in totals.items())
    print(f"[openalex_bulk] complete: {message}")
    logger.info("openalex_bulk complete: %s", message)
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-pages", type=int, default=None)
    args = parser.parse_args()
    run(limit_pages=args.limit_pages)


if __name__ == "__main__":
    main()
