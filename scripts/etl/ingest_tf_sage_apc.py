"""Per-journal APC lookup for Taylor & Francis and SAGE - on-demand
functions plus a rate-limited bulk sweep.

Confirmed live this session: neither publisher exposes a bulk APC file
(T&F's own price-lists page only has subscription-tier PDFs; SAGE has
no bulk export either) - both require a per-journal page fetch, so this
is inherently one HTTP request per journal either way. `fetch_tf_apc`/
`fetch_sage_apc` are usable standalone for a single lookup when a
specific journal is viewed in the app (src/blueprints/journals.py);
`run()` sweeps every T&F/SAGE journal already in the DB that has a
homepage_url, queued and rate-limited rather than run interactively -
still large (~1,900 T&F + ~1,150 SAGE journals total, though only a
fraction have a homepage_url until the OpenAlex enrichment pass fills
more in).

Real blocker found live (2026-08-18), not assumed: plain `requests`
gets HTTP 403 on tandfonline.com journal pages - `cloudscraper` gets
through (200) - but neither T&F's `/journals/{code}` page, its
`/{code}/about-this-journal` sub-page, nor SAGE's `/home/{code}` page
actually contain an APC dollar figure in the fetched page text (checked
directly: zero "APC" mentions, zero dollar-amount matches, on real
journal pages for both publishers). T&F's real APC figure lives behind
its separate "Open Access Cost Finder" tool (an interactive page, not
plain HTML in the journal page) - not reverse-engineered here. So
`fetch_tf_apc`/`fetch_sage_apc` below are honest best-effort parsers
that correctly return `None` on real pages today, and `run()` will
report near-100% `failed` until the real APC page/API is located for
each publisher - that's accurate, not a bug to silence.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup


def _scraper():
    import cloudscraper
    return cloudscraper.create_scraper()


def fetch_tf_apc(journal_slug_or_url: str):
    """journal_slug_or_url: a tandfonline.com journal homepage URL, e.g.
    https://www.tandfonline.com/journals/tjhs20"""
    try:
        resp = _scraper().get(journal_slug_or_url, timeout=20)
        resp.raise_for_status()
    except Exception:
        return None
    match = re.search(r"APC[^$]{0,40}\$?([\d,]{3,6})", resp.text)
    if not match:
        return None
    return {"apc_amount": float(match.group(1).replace(",", "")), "currency": "USD",
            "source_url": journal_slug_or_url}


def fetch_sage_apc(journal_url: str):
    """journal_url: a journals.sagepub.com journal homepage URL."""
    try:
        resp = _scraper().get(journal_url, timeout=20)
        resp.raise_for_status()
    except Exception:
        return None
    soup = BeautifulSoup(resp.text, "lxml")
    text = soup.get_text(" ", strip=True)
    match = re.search(r"APC[^$]{0,40}\$?([\d,]{3,6})", text)
    if not match:
        return None
    return {"apc_amount": float(match.group(1).replace(",", "")), "currency": "USD",
            "source_url": journal_url}


def run(limit: int = 1000):
    """Bulk-sweeps journals already in the DB that have a homepage_url and a
    T&F/SAGE publisher - still one HTTP request per journal (no bulk file
    exists for either), just queued and rate-limited instead of purely
    on-demand. Journals without a homepage_url are skipped here, not
    guessed at - run scripts/etl/ingest_openalex_enrichment.py first to
    backfill more homepage_urls, then re-run this."""
    import datetime
    import time as _time

    from common import etl_run, upsert_publisher_apc
    from src.db.engine import session_scope
    from src.db.models import Journal

    snapshot_date = datetime.datetime.utcnow()

    with etl_run("tf_sage_apc") as counters:
        with session_scope() as session:
            targets = (
                session.query(Journal)
                .filter(
                    Journal.homepage_url.isnot(None),
                    (Journal.publisher.ilike("%taylor%")) | (Journal.publisher.ilike("%sage%")),
                )
                .limit(limit)
                .all()
            )
            for journal in targets:
                counters.fetched += 1
                is_tf = "taylor" in (journal.publisher or "").lower()
                fetcher = fetch_tf_apc if is_tf else fetch_sage_apc
                publisher_key = "tandf" if is_tf else "sage"
                try:
                    result = fetcher(journal.homepage_url)
                except Exception:
                    result = None
                _time.sleep(0.4)
                if result is None or result.get("apc_amount") is None:
                    counters.failed += 1
                    continue
                upsert_publisher_apc(
                    session, journal.id, publisher=publisher_key, list_type="unknown",
                    apc_amount=result["apc_amount"], currency=result.get("currency", "USD"),
                    source_url=result.get("source_url", journal.homepage_url), snapshot_date=snapshot_date,
                )
                counters.upserted += 1
                if counters.upserted % 50 == 0:
                    session.commit()


if __name__ == "__main__":
    run()
