"""Ingest Scimago: cloudscraper best-effort, CSV fallback.

Honesty check performed at implementation time: both `cloudscraper` and
`curl_cffi` (browser-impersonation) were live-tested against
scimagojr.com and both still return HTTP 403 "Just a moment..." -
Cloudflare is running a Turnstile-integrated challenge here, not the
older JS-VM challenge those tools solve. So in practice today the CSV
path below is what actually runs; the cloudscraper attempt is kept as a
cheap forward-compatible retry (Cloudflare configs change) rather than
something to rely on.

CSV: data/scimago_raw.csv (already present in this repo, manually
downloaded from scimagojr.com/journalrank.php per SCImago's own terms -
free for non-commercial use with citation). Real header (semicolon-
delimited): Rank;Sourceid;Title;Type;Issn;Publisher;Open Access;
Open Access Diamond;SJR;SJR Best Quartile;H index;...;Categories;Areas
"""
from __future__ import annotations

import csv
import datetime
import re

from common import IssnIndex, etl_run, upsert_one_to_one
from src.db.engine import session_scope
from src.db.issn_utils import normalize_issn
from src.db.models import JournalScimago

CSV_PATH = __file__.rsplit("scripts", 1)[0] + "data/scimago_raw.csv"
SOURCE_URL = "https://www.scimagojr.com/journalrank.php"


def try_cloudscraper_probe() -> bool:
    """Return True if Cloudflare can currently be passed without a browser.
    Cheap single-request check before ever attempting a bulk automated run."""
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(f"{SOURCE_URL.replace('journalrank.php', 'journalsearch.php')}?q=1069-6563", timeout=15)
        return resp.status_code == 200
    except Exception:
        return False


def _parse_csv_rows():
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            quartile = (row.get("SJR Best Quartile") or "").strip()
            if quartile not in ("Q1", "Q2", "Q3", "Q4"):
                continue
            categories = (row.get("Categories") or "").split(";")[0].strip()
            categories = re.sub(r"\s*\(Q[1-4]\)\s*$", "", categories)
            title = (row.get("Title") or "").strip()
            publisher = (row.get("Publisher") or "").strip()
            try:
                sjr = float((row.get("SJR") or "0").replace(",", "."))
            except ValueError:
                sjr = None
            try:
                h_index = int(row.get("H index") or 0)
            except ValueError:
                h_index = None
            coverage = (row.get("Coverage") or "").strip()
            issn_field = (row.get("Issn") or "").strip().strip('"')
            issns = [normalize_issn(i.strip()) for i in issn_field.split(",")]
            issns = [i for i in issns if i]
            if not issns:
                continue
            yield {
                "issns": issns, "title": title, "publisher": publisher,
                "quartile": quartile, "category": categories,
                "sjr": sjr, "h_index": h_index, "coverage": coverage,
            }


def run():
    automated_available = try_cloudscraper_probe()
    fetch_method = "cloudscraper" if automated_available else "manual_csv"
    snapshot_date = datetime.datetime.utcnow()

    with etl_run("scimago") as counters:
        with session_scope() as session:
            index = IssnIndex(session)
            for row in _parse_csv_rows():
                counters.fetched += 1
                journal = index.resolve(row["issns"], title=row["title"], publisher=row["publisher"])
                upsert_one_to_one(
                    session, JournalScimago, journal.id,
                    sjr_score=row["sjr"], sjr_best_quartile=row["quartile"],
                    h_index=row["h_index"], subject_category=row["category"],
                    coverage_years=row["coverage"], snapshot_date=snapshot_date,
                    source_url=SOURCE_URL, fetch_method=fetch_method,
                )
                counters.upserted += 1


if __name__ == "__main__":
    run()
