"""Ingest an OpenAlex-based CiteScore *estimate*, for journals where the
real Scopus CiteScore is unknown.

Real CiteScore isn't reachable via any source we have automated,
unauthenticated access to (confirmed live, 2026-08-18): the real Scopus
Source List xlsx has no CiteScore/Percentile columns at all;
scopus.com and ScienceDirect journal pages are both Cloudflare/captcha-
blocked; Elsevier's public CiteScore page only links a marketing PDF,
no bulk data file.

OpenAlex's free, no-login `/sources/issn:{issn}` endpoint returns
`summary_stats.2yr_mean_citedness` - not the same formula as CiteScore
(different citation window/methodology) but a legitimate, live,
citable citation-rate proxy. This repo's own pre-SQL pipeline
(scripts/build_journal_index.py) already used exactly this field as an
honestly-labeled "estimated" tier. Written into `citescore_estimated` /
`citescore_estimate_source` - never into the real `citescore` column,
which must stay NULL until a verified Scopus figure exists.
"""
from __future__ import annotations

import datetime
import time

import requests

from common import etl_run
from src.db.engine import session_scope
from src.db.models import Journal, JournalScopus

OPENALEX_URL = "https://api.openalex.org/sources/issn:{issn}"
SOURCE_LABEL = "openalex_2yr_mean_citedness"
_DELAY_S = 0.15  # polite, OpenAlex has no strict published rate limit but this is a public API


def _fetch_citedness(issn: str):
    resp = requests.get(OPENALEX_URL.format(issn=issn), timeout=15,
                         headers={"User-Agent": "research-agent-journal-db (mailto:harishvidyarth.n.2024.csecs@rajalakshmi.edu.in)"})
    if resp.status_code != 200:
        return None
    stats = (resp.json() or {}).get("summary_stats") or {}
    value = stats.get("2yr_mean_citedness")
    return float(value) if value is not None else None


def run(limit: int = 500):
    """Only backfills journals missing BOTH a real citescore and an
    existing estimate, so re-runs are cheap and incremental."""
    snapshot_date = datetime.datetime.utcnow()

    with etl_run("openalex_citescore_estimate") as counters:
        with session_scope() as session:
            targets = (
                session.query(Journal)
                .outerjoin(JournalScopus, JournalScopus.journal_id == Journal.id)
                .filter(
                    (JournalScopus.id.is_(None))
                    | ((JournalScopus.citescore.is_(None)) & (JournalScopus.citescore_estimated.is_(None)))
                )
                .limit(limit)
                .all()
            )
            for journal in targets:
                counters.fetched += 1
                try:
                    estimate = _fetch_citedness(journal.issn_l)
                except Exception:
                    counters.failed += 1
                    time.sleep(_DELAY_S)
                    continue
                time.sleep(_DELAY_S)
                if estimate is None:
                    counters.failed += 1
                    continue

                scopus_row = session.query(JournalScopus).filter_by(journal_id=journal.id).one_or_none()
                if scopus_row is None:
                    scopus_row = JournalScopus(journal_id=journal.id, snapshot_date=snapshot_date)
                    session.add(scopus_row)
                scopus_row.citescore_estimated = estimate
                scopus_row.citescore_estimate_source = SOURCE_LABEL
                counters.upserted += 1

                if counters.upserted % 100 == 0:
                    # Commit periodically instead of once at the very end -
                    # this loop can run for hours; a single giant transaction
                    # would lose all progress on any crash/interruption and
                    # write-lock the shared SQLite file for the whole run.
                    session.commit()


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    run(limit=n)
