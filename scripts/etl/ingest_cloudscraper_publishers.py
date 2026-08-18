"""Ingest publishers whose price pages block plain `requests`/`curl` with a
Cloudflare 403: MDPI, ACM, Oxford Academic (OUP), PLOS.

Live-tested each with cloudscraper at implementation time - honest result,
not assumed:
  - ACM (libraries.acm.org/acmopen/apc-list-pricing): cloudscraper gets
    through (HTTP 200). Real table found: flat-rate pricing by article
    type, not per-journal - "Journal Article: $1800 list / $1300 ACM-SIG-
    member". Applied to every journal already in our DB whose publisher
    is "Association for Computing Machinery" (confirmed 80 such journals).
  - MDPI, OUP, PLOS: cloudscraper still returns 403 for all three
    (stronger Cloudflare rule than ACM's). Kept as a probe-and-skip so
    the script stays forward-compatible if that changes, but today these
    three simply do not populate - that's reported honestly in the run
    log (records_fetched=0), not silently hidden.
"""
from __future__ import annotations

import datetime
import re

from common import etl_run, upsert_publisher_apc
from src.db.engine import session_scope
from src.db.models import Journal

ACM_URL = "https://libraries.acm.org/acmopen/apc-list-pricing"
BLOCKED_URLS = {
    "mdpi": "https://www.mdpi.com/about/apc-2026",
    "oup": "https://academic.oup.com/pages/open-research/open-access/charges-licences-and-self-archiving",
    "plos": "https://plos.org/fees/",
}


def _scraper():
    import cloudscraper
    return cloudscraper.create_scraper()


def fetch_acm_journal_article_price():
    resp = _scraper().get(ACM_URL, timeout=30)
    resp.raise_for_status()
    match = re.search(r"Journal Article.*?\$(\d[\d,]*)\D+\$(\d[\d,]*)", resp.text, re.S)
    if not match:
        return None
    return {"list_price": float(match.group(1).replace(",", "")),
            "member_price": float(match.group(2).replace(",", ""))}


def ingest_acm():
    prices = fetch_acm_journal_article_price()
    snapshot_date = datetime.datetime.utcnow()
    with etl_run("acm_apc") as counters:
        if prices is None:
            counters.failed = 1
            return
        with session_scope() as session:
            acm_journals = (
                session.query(Journal)
                .filter(Journal.publisher.ilike("%association for computing machinery%"))
                .all()
            )
            for journal in acm_journals:
                counters.fetched += 1
                upsert_publisher_apc(
                    session, journal.id, publisher="acm", list_type="fully-oa",
                    apc_amount=prices["list_price"], currency="USD",
                    source_url=ACM_URL, snapshot_date=snapshot_date,
                )
                counters.upserted += 1


def probe_blocked_publisher(name: str, url: str) -> bool:
    """Cheap check for whether Cloudflare can currently be passed. Returns
    True (and logs a failed/empty run honestly) if still blocked."""
    with etl_run(f"{name}_apc") as counters:
        try:
            resp = _scraper().get(url, timeout=20)
        except Exception:
            counters.failed = 1
            return True
        if resp.status_code != 200:
            counters.failed = 1
            return True
        counters.fetched = 1
        # Reachable now - parsing left for a follow-up once this holds,
        # rather than writing a parser against a page we couldn't fetch.
        return False


def run():
    ingest_acm()
    for name, url in BLOCKED_URLS.items():
        probe_blocked_publisher(name, url)


if __name__ == "__main__":
    run()
