"""Ingest IEEE's official APC price list (PDF table).

Source: https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/sites/7/IEEE-Article-Processing-Charges-List.pdf
Verified live this session (HTTP 200, real PDF, no login).

Real constraint found by inspecting the actual table: IEEE's list has
NO ISSN column at all - only Title (e.g. "Aerospace and Electronic
Systems, IEEE Trans.") and Acronym (e.g. "TAES"). Since we can't join
on ISSN, this matches against titles already in the `journals` table
using a strict normalized-word heuristic (both sides: lowercase, strip
"ieee"/"trans"/punctuation, compare as word sets). Rows that don't hit
a confident match are counted as failed/unmatched, never guessed onto
the wrong journal - IEEE not publishing ISSNs here is a real gap, not
something to paper over.
"""
from __future__ import annotations

import datetime
import re

import pdfplumber
import requests

from common import etl_run, upsert_publisher_apc
from src.db.engine import session_scope
from src.db.models import Journal

URL = "https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/sites/7/IEEE-Article-Processing-Charges-List.pdf"
PUBLISHER = "ieee"
_STOPWORDS = {"ieee", "trans", "transactions", "journal", "journals", "of", "on",
              "the", "and", "mag", "magazine", "letters", "letter"}


def _normalize_title(title: str) -> frozenset:
    words = re.sub(r"[^a-z0-9 ]", " ", title.lower()).split()
    return frozenset(w for w in words if w not in _STOPWORDS and len(w) > 2)


def _fetch_pdf_bytes() -> bytes:
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()
    return resp.content


def _parse_amount(cell):
    if not cell:
        return None
    match = re.search(r"[\d,]+", cell.split("/")[0])
    return float(match.group().replace(",", "")) if match else None


def _parse_rows(pdf_bytes: bytes):
    import io
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue
            for row in table:
                if not row or not row[0] or row[0] in ("Title", None):
                    continue
                title, acronym, oa_type = row[0], row[1], row[2]
                oa_fee = row[3] if len(row) > 3 else None
                title = title.replace("\n", " ").strip()
                if not title or (oa_type or "").strip().lower() == "no oa":
                    continue
                yield {
                    "title": title, "acronym": (acronym or "").strip(),
                    "list_type": (oa_type or "").strip().lower(),
                    "apc_amount": _parse_amount(oa_fee),
                }


def _build_title_index(session):
    index = {}
    for journal in session.query(Journal.id, Journal.title).all():
        key = _normalize_title(journal.title)
        if key and key not in index:
            index[key] = journal.id
    return index


def run():
    pdf_bytes = _fetch_pdf_bytes()
    snapshot_date = datetime.datetime.utcnow()

    with etl_run(f"{PUBLISHER}_apc") as counters:
        with session_scope() as session:
            title_index = _build_title_index(session)
            for row in _parse_rows(pdf_bytes):
                counters.fetched += 1
                key = _normalize_title(row["title"])
                journal_id = title_index.get(key)
                if journal_id is None:
                    counters.failed += 1
                    continue
                upsert_publisher_apc(
                    session, journal_id, publisher=PUBLISHER, list_type=row["list_type"],
                    apc_amount=row["apc_amount"], currency="USD",
                    source_url=URL, snapshot_date=snapshot_date,
                )
                counters.upserted += 1


if __name__ == "__main__":
    run()
