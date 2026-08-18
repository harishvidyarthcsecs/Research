"""Ingest Frontiers: category price table + on-demand per-journal APC.

Source: https://www.frontiersin.org/about/fee-policy - verified live
(HTTP 200), a real 4-category x 3-article-type CHF price table.

Real constraint found by inspecting both the fee-policy page and a
per-journal fees page (frontiersin.org/journals/medicine/for-authors/
publishing-fees, confirmed live with a real table: "Frontiers in
Medicine | CHF 3,150 | CHF 2,500 | 0"): neither carries an ISSN, only
the journal's display name. Same title-normalized matching as IEEE, and
same honesty rule - unmatched titles are skipped, never guessed.

Frontiers' journal directory (~200+ titles) is JS-rendered and wasn't
enumerable from static HTML at implementation time, so bulk per-journal
ingestion isn't automated here - `fetch_journal_apc(slug)` is exposed
for on-demand lookup (same "no bulk file, look up per journal" pattern
as Taylor & Francis / SAGE) and `run()` takes an explicit slug list.
"""
from __future__ import annotations

import datetime
import re

import requests
from bs4 import BeautifulSoup

from common import etl_run, upsert_publisher_apc
from src.db.engine import session_scope
from src.db.models import Journal

FEE_POLICY_URL = "https://www.frontiersin.org/about/fee-policy"
JOURNAL_FEES_URL = "https://www.frontiersin.org/journals/{slug}/for-authors/publishing-fees"
PUBLISHER = "frontiers"
_STOPWORDS = {"frontiers", "in", "of", "the", "and"}

# A starter set; extend as more Frontiers journals are looked up. Not
# exhaustive - Frontiers' full directory needs its JS-rendered API
# resolved separately, documented as a follow-up rather than guessed here.
DEFAULT_SLUGS = ["medicine", "psychology", "psychiatry", "public-health", "neuroscience"]


def fetch_category_price_table() -> list:
    resp = requests.get(FEE_POLICY_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table")
    if table is None:
        return []
    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) >= 5:
            rows.append({
                "category": cells[0], "description": cells[1],
                "type_a_chf": cells[2], "type_b_chf": cells[3], "type_c_chf": cells[4],
            })
    return rows


def _normalize_title(title: str) -> frozenset:
    words = re.sub(r"[^a-z0-9 ]", " ", title.lower()).split()
    return frozenset(w for w in words if w not in _STOPWORDS and len(w) > 2)


def _parse_chf(cell: str):
    match = re.search(r"[\d,]+", cell or "")
    return float(match.group().replace(",", "")) if match else None


def fetch_journal_apc(slug: str):
    resp = requests.get(JOURNAL_FEES_URL.format(slug=slug), timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table")
    if table is None:
        return None
    rows = table.find_all("tr")
    if len(rows) < 2:
        return None
    cells = [td.get_text(strip=True) for td in rows[1].find_all("td")]
    if len(cells) < 2:
        return None
    return {"title": cells[0], "apc_amount": _parse_chf(cells[1]), "currency": "CHF"}


def run(slugs=None):
    slugs = slugs or DEFAULT_SLUGS
    snapshot_date = datetime.datetime.utcnow()

    with etl_run(f"{PUBLISHER}_apc") as counters:
        with session_scope() as session:
            title_index = {
                _normalize_title(t): jid
                for jid, t in session.query(Journal.id, Journal.title).all()
            }
            for slug in slugs:
                counters.fetched += 1
                try:
                    result = fetch_journal_apc(slug)
                except Exception:
                    counters.failed += 1
                    continue
                if result is None:
                    counters.failed += 1
                    continue
                journal_id = title_index.get(_normalize_title(result["title"]))
                if journal_id is None:
                    counters.failed += 1
                    continue
                upsert_publisher_apc(
                    session, journal_id, publisher=PUBLISHER, list_type="fully-oa",
                    apc_amount=result["apc_amount"], currency=result["currency"],
                    source_url=JOURNAL_FEES_URL.format(slug=slug), snapshot_date=snapshot_date,
                )
                counters.upserted += 1


if __name__ == "__main__":
    run()
