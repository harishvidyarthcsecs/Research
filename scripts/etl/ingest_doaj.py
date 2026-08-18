"""Ingest DOAJ: bulk CSV baseline + live per-ISSN cross-check.

CSV: data/incoming/doaj_journalcsv_20260712_2320_utf8.csv (user-supplied
DOAJ export, snapshot dated 2026-07-12, 23,184 rows - loaded as the
baseline since it's fast and complete).

Live cross-check: https://doaj.org/api/search/journals/issn:{issn}
(confirmed live, no auth) - the CSV is known stale-prone, so re-checking
a batch of ISSNs against the live API on each run surfaces drift
(diverged_from_csv flag) rather than silently trusting a dated file.
Full-corpus live-check is rate-limited and meant to run incrementally
across many scheduled runs, not all 23k rows in one pass.
"""
from __future__ import annotations

import csv
import datetime
import os
import time

import requests

from common import IssnIndex, etl_run, upsert_one_to_one
from src.db.engine import session_scope
from src.db.issn_utils import normalize_issn
from src.db.models import JournalDOAJ

CSV_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "incoming",
    "doaj_journalcsv_20260712_2320_utf8.csv",
)
CSV_SNAPSHOT_DATE = datetime.datetime(2026, 7, 12, 23, 20)
LIVE_API = "https://doaj.org/api/search/journals/issn:{issn}"


def _parse_apc(row: dict):
    has_apc = (row.get("APC") or "").strip().lower() == "yes"
    amount_raw = (row.get("APC amount") or "").strip()
    amount, currency = None, None
    if amount_raw:
        parts = amount_raw.split()
        if len(parts) == 2 and parts[0].replace(".", "", 1).isdigit():
            amount, currency = float(parts[0]), parts[1]
    return has_apc, amount, currency


def _bulk_rows():
    with open(CSV_PATH, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            issn_print = row.get("Journal ISSN (print version)")
            issn_online = row.get("Journal EISSN (online version)")
            if not normalize_issn(issn_print) and not normalize_issn(issn_online):
                continue
            has_apc, amount, currency = _parse_apc(row)
            yield {
                "issn_print": issn_print,
                "issn_online": issn_online,
                "title": row.get("Journal title", ""),
                "publisher": row.get("Publisher", ""),
                "country": row.get("Country of publisher", ""),
                "homepage_url": row.get("Journal URL", ""),
                "has_apc": has_apc,
                "apc_amount": amount,
                "apc_currency": currency,
                "waiver_text": row.get("Journal waiver policy (for developing country authors etc)", ""),
                "waiver_url": row.get("Waiver policy information URL", ""),
                "license_type": row.get("Journal license", ""),
                "review_process": row.get("Review process", ""),
            }


def bulk_load():
    with etl_run("doaj_csv_baseline") as counters:
        with session_scope() as session:
            index = IssnIndex(session)
            for row in _bulk_rows():
                counters.fetched += 1
                journal = index.resolve(
                    [row["issn_print"], row["issn_online"]], title=row["title"],
                    publisher=row["publisher"], country=row["country"],
                    homepage_url=row["homepage_url"],
                )
                upsert_one_to_one(
                    session, JournalDOAJ, journal.id,
                    in_doaj=True, has_apc=row["has_apc"],
                    apc_amount=row["apc_amount"], apc_currency=row["apc_currency"],
                    waiver_policy_text=row["waiver_text"], waiver_policy_url=row["waiver_url"],
                    license_type=row["license_type"], review_process=row["review_process"],
                    csv_snapshot_date=CSV_SNAPSHOT_DATE,
                )
                counters.upserted += 1


def _live_lookup(issn: str, timeout: int = 10):
    resp = requests.get(LIVE_API.format(issn=issn), timeout=timeout)
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        return None
    bib = results[0].get("bibjson") or {}
    apc = bib.get("apc") or {}
    prices = apc.get("max") or []
    return {
        "has_apc": apc.get("has_apc"),
        "apc_amount": prices[0]["price"] if prices else None,
        "apc_currency": prices[0]["currency"] if prices else None,
        "license_type": (bib.get("license") or [{}])[0].get("type", ""),
        "review_process": ",".join((bib.get("editorial") or {}).get("review_process") or []),
    }


def live_cross_check(limit: int = 200, delay_s: float = 0.6):
    """Re-check a batch of ISSNs against the live API, flagging drift from the CSV."""
    now = datetime.datetime.utcnow()
    with etl_run("doaj_live_check") as counters:
        with session_scope() as session:
            rows = (
                session.query(JournalDOAJ)
                .filter(JournalDOAJ.live_checked_at.is_(None))
                .limit(limit)
                .all()
            )
            for doaj_row in rows:
                counters.fetched += 1
                try:
                    live = _live_lookup(doaj_row.journal.issn_l)
                except Exception:
                    counters.failed += 1
                    time.sleep(delay_s)
                    continue
                doaj_row.live_checked_at = now
                if live is not None:
                    diverged = (
                        live["has_apc"] != doaj_row.has_apc
                        or (live["apc_amount"] or None) != (doaj_row.apc_amount or None)
                    )
                    doaj_row.diverged_from_csv = diverged
                    if diverged:
                        doaj_row.has_apc = live["has_apc"]
                        doaj_row.apc_amount = live["apc_amount"]
                        doaj_row.apc_currency = live["apc_currency"]
                counters.upserted += 1
                time.sleep(delay_s)


def run(live_check_limit: int = 0):
    bulk_load()
    if live_check_limit > 0:
        live_cross_check(limit=live_check_limit)


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    run(live_check_limit=n)
