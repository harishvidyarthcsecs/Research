"""Ingest Wiley's official APC price lists (fully-OA + Hybrid).

Sources, both verified live this session (HTTP 200, real .xlsx, no login):
  - https://authors.wiley.com/asset/Wiley-Journal-APCs-Open-Access.xlsx
  - https://authors.wiley.com/asset/Wiley-Journal-APCs-OnlineOpen.xlsx

Actual structure (inspected directly): a few metadata rows, then a
header row with journal name/title, subject area, an "Online ISSN"
column stored as a bare integer (leading zeros lost by Excel - restored
here via zero-padding to 8 digits before normalizing), license types,
and USD/GBP/EUR price columns.
"""
from __future__ import annotations

import datetime
import io

import openpyxl
import requests

from common import etl_run, get_or_create_journal, upsert_publisher_apc
from src.db.engine import session_scope
from src.db.issn_utils import normalize_issn

PUBLISHER = "wiley"
SOURCES = [
    ("fully-oa", "https://authors.wiley.com/asset/Wiley-Journal-APCs-Open-Access.xlsx",
     "Journal Name", "Online ISSN", "USD"),
    ("hybrid", "https://authors.wiley.com/asset/Wiley-Journal-APCs-OnlineOpen.xlsx",
     "Journal Title", "Online\nISSN", "USD $"),
]


def _fetch_workbook(url: str):
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return openpyxl.load_workbook(io.BytesIO(resp.content), read_only=True, data_only=True)


def _issn_from_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return normalize_issn(str(int(value)).zfill(8))
    return normalize_issn(str(value))


def _parse_rows(ws, title_col: str, issn_col: str, price_col: str):
    header = None
    rows_iter = ws.iter_rows(values_only=True)
    for row in rows_iter:
        if title_col in (row or ()) and issn_col in (row or ()):
            header = row
            break
    if header is None:
        return
    idx = {name: pos for pos, name in enumerate(header) if name is not None}
    title_i, issn_i, price_i = idx.get(title_col), idx.get(issn_col), idx.get(price_col)
    if title_i is None or issn_i is None:
        return
    for row in rows_iter:
        if row is None or title_i >= len(row) or issn_i >= len(row):
            continue
        title, issn_raw = row[title_i], row[issn_i]
        issn_l = _issn_from_cell(issn_raw)
        if not issn_l or not title:
            continue
        price = row[price_i] if price_i is not None and price_i < len(row) else None
        apc_amount = price if isinstance(price, (int, float)) else None
        yield {"issn_l": issn_l, "title": str(title).strip(), "apc_amount": apc_amount}


def run():
    snapshot_date = datetime.datetime.utcnow()
    for list_type, url, title_col, issn_col, price_col in SOURCES:
        wb = _fetch_workbook(url)
        ws = wb.active
        with etl_run(f"wiley_apc_{list_type}") as counters:
            with session_scope() as session:
                for row in _parse_rows(ws, title_col, issn_col, price_col):
                    counters.fetched += 1
                    journal = get_or_create_journal(session, row["issn_l"], title=row["title"], publisher="Wiley")
                    upsert_publisher_apc(
                        session, journal.id, publisher=PUBLISHER, list_type=list_type,
                        apc_amount=row["apc_amount"], currency="USD",
                        source_url=url, snapshot_date=snapshot_date,
                    )
                    counters.upserted += 1


if __name__ == "__main__":
    run()
