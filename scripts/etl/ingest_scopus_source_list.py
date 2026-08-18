"""Ingest Elsevier's official Scopus Source List (manual download).

scopus.com itself is Cloudflare-blocked (confirmed live: 403 "Sorry, you
have been blocked") - the legitimate route is Elsevier's free public
Scopus Source List XLSX (no API key), downloaded manually and placed at
data/incoming/scopus_source_list.xlsx.

Verified against a real file (ext_list_Jul_2026.xlsx, 48,888 rows, main
data on the "Scopus Sources ..." sheet): real headers are `Source Title,
ISSN, EISSN, Active or Inactive, Coverage, ..., All Science Journal
Classification Codes (ASJC)`. Header-text matching (not exact-string
assertions) still used since Elsevier could reorder/rename columns
between releases.

`citescore`/`percentile` are intentionally detected but will always end
up None from this file - confirmed by exhaustively grepping every header
across all 7 sheets of a real download: Elsevier ships CiteScore
separately (via scopus.com itself, which is Cloudflare-blocked per
above), not in the title-list export. Not a broken match; there is
nothing to match here.
"""
from __future__ import annotations

import datetime
import os

import openpyxl

from common import IssnIndex, etl_run, upsert_one_to_one
from src.db.engine import session_scope
from src.db.issn_utils import normalize_issn
from src.db.models import JournalScopus

XLSX_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "incoming", "scopus_source_list.xlsx",
)
SOURCE_URL = "https://www.elsevier.com/products/scopus/scopus-title-list"


def _find_columns(header_row):
    cols = {}
    for idx, cell in enumerate(header_row):
        label = str(cell or "").strip().lower()
        if "title" in label and "source" in label:
            cols.setdefault("title", idx)
        elif "issn" in label and "e-issn" not in label and "eissn" not in label:
            cols.setdefault("issn", idx)
        elif "eissn" in label or "e-issn" in label:
            cols.setdefault("eissn", idx)
        elif "citescore" in label:
            cols.setdefault("citescore", idx)
        elif "percentile" in label:
            cols.setdefault("percentile", idx)
        elif "asjc" in label:
            cols.setdefault("asjc", idx)
        elif "active" in label and "inactive" in label:
            # Requires BOTH substrings, not just "active" or "status" alone -
            # "Open Access Status" also contains "status" and would otherwise
            # be picked instead of "Active or Inactive" by column-order luck.
            cols.setdefault("status", idx)
        elif "coverage" in label:
            cols.setdefault("coverage", idx)
    return cols


def _parse_rows(ws):
    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter, None)
    if header is None:
        return
    cols = _find_columns(header)
    if "title" not in cols or "issn" not in cols:
        return
    for row in rows_iter:
        title = row[cols["title"]] if cols["title"] < len(row) else None

        def _get(name):
            idx = cols.get(name)
            return row[idx] if idx is not None and idx < len(row) else None

        issn_raw = _get("issn")
        eissn_raw = _get("eissn")
        issn = normalize_issn(str(issn_raw) if issn_raw else "")
        eissn = normalize_issn(str(eissn_raw) if eissn_raw else "")
        if not (issn or eissn) or not title:
            continue

        yield {
            "issn": issn, "eissn": eissn, "title": str(title).strip(),
            "citescore": _get("citescore"), "percentile": _get("percentile"),
            "asjc_codes": str(_get("asjc") or ""), "active_status": str(_get("status") or ""),
            "coverage_years": str(_get("coverage") or ""),
        }


def run():
    if not os.path.exists(XLSX_PATH):
        print(f"[scopus_source_list] {XLSX_PATH} not found - download from "
              f"{SOURCE_URL} and place it there. Skipping.")
        return

    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    ws = wb.active
    snapshot_date = datetime.datetime.utcnow()

    with etl_run("scopus_source_list") as counters:
        with session_scope() as session:
            index = IssnIndex(session)
            for row in _parse_rows(ws):
                counters.fetched += 1
                try:
                    citescore = float(row["citescore"]) if row["citescore"] not in (None, "") else None
                except (TypeError, ValueError):
                    citescore = None
                try:
                    percentile = float(row["percentile"]) if row["percentile"] not in (None, "") else None
                except (TypeError, ValueError):
                    percentile = None
                journal = index.resolve([row["issn"], row["eissn"]], title=row["title"])
                upsert_one_to_one(
                    session, JournalScopus, journal.id,
                    citescore=citescore, percentile=percentile,
                    asjc_codes=row["asjc_codes"][:200], active_status=row["active_status"][:20],
                    coverage_years=row["coverage_years"][:50], snapshot_date=snapshot_date,
                )
                counters.upserted += 1


if __name__ == "__main__":
    run()
