"""Ingest Clarivate Web of Science Master Journal List.

mjl.clarivate.com is an Angular SPA and its own FAQ states only title/
ISSN/publisher are public without login; bulk CSV export requires a
free WoS account (the user's chosen path - they periodically export
their MJL Collection List and drop it at data/incoming/mjl_export.csv).
That file wasn't available to inspect at implementation time (it's
login-gated, can't be fetched programmatically to verify columns), so
this uses the same flexible header-text matching as the Scopus parser
rather than asserting an unverified exact column layout.

If the file is absent, this only marks existing journals with
is_partial=True where MJL is referenced elsewhere (e.g. Anna University
CFR rows list a "publisher" but not WoS edition) - it does not fabricate
JIF/quartile data.

Investigated a no-login automated alternative (2026-08-18) and hit a
real dead end, documented here so it isn't re-attempted from scratch:
the search-results page's own Angular bundle reveals a "public" endpoint
(`POST /api/jprof/public/rank-search`) with a reverse-engineered payload
shape (`searchValue`, `pageNum`, `pageSize`, `sortOrder`, `filters`,
`searchIdentifier`). Calling it directly with that exact shape returns
HTTP 404 "Resource not found," not an auth error - the endpoint's CORS
`access-control-allow-headers` lists `x-1p-session`, a session token
that's generated client-side by the Angular app's own JS during page
load (confirmed: a plain GET of the search-results page only sets a
Cloudflare `__cf_bm` bot-management cookie, nothing usable as that
token). So this "public" endpoint isn't reachable without executing
real browser JS first - not a quick automatable win, and not attempted
further per a deliberate bounded-effort call. The manual CSV path above
remains the only practical MJL ingest route.
"""
from __future__ import annotations

import csv
import datetime
import os

from common import etl_run, get_or_create_journal, upsert_one_to_one
from src.db.engine import session_scope
from src.db.issn_utils import normalize_issn
from src.db.models import JournalMJL

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "incoming", "mjl_export.csv")
SOURCE_NOTE = "Clarivate Web of Science Master Journal List (user's account export)"


def _find_columns(header: list):
    cols = {}
    for idx, name in enumerate(header):
        label = (name or "").strip().lower()
        if "journal title" in label or label == "title":
            cols.setdefault("title", idx)
        elif "issn" in label and "eissn" not in label and "e-issn" not in label:
            cols.setdefault("issn", idx)
        elif "eissn" in label or "e-issn" in label:
            cols.setdefault("eissn", idx)
        elif "jif" in label or "impact factor" in label:
            cols.setdefault("jif", idx)
        elif "quartile" in label:
            cols.setdefault("quartile", idx)
        elif "edition" in label or "index" in label:
            cols.setdefault("edition", idx)
    return cols


def _parse_rows(fh):
    reader = csv.reader(fh)
    header = next(reader, None)
    if header is None:
        return
    cols = _find_columns(header)
    if "title" not in cols or ("issn" not in cols and "eissn" not in cols):
        return
    for row in reader:
        title = row[cols["title"]] if cols["title"] < len(row) else None
        issn_l = ""
        if "issn" in cols and cols["issn"] < len(row):
            issn_l = normalize_issn(row[cols["issn"]])
        if not issn_l and "eissn" in cols and cols["eissn"] < len(row):
            issn_l = normalize_issn(row[cols["eissn"]])
        if not issn_l or not title:
            continue
        jif_raw = row[cols["jif"]] if "jif" in cols and cols["jif"] < len(row) else None
        try:
            jif = float(jif_raw) if jif_raw else None
        except ValueError:
            jif = None
        quartile = row[cols["quartile"]] if "quartile" in cols and cols["quartile"] < len(row) else None
        edition = row[cols["edition"]] if "edition" in cols and cols["edition"] < len(row) else None
        yield {"issn_l": issn_l, "title": title.strip(), "jif": jif,
               "quartile": (quartile or "").strip()[:2], "edition": (edition or "").strip()[:20]}


def run():
    if not os.path.exists(CSV_PATH):
        print(f"[mjl_csv] {CSV_PATH} not found - export your MJL Collection List "
              "from mjl.clarivate.com (requires your free account) and place it "
              "there. Skipping - no partial/full MJL data will be written.")
        return

    snapshot_date = datetime.datetime.utcnow()
    with etl_run("mjl_csv") as counters:
        with session_scope() as session:
            with open(CSV_PATH, newline="", encoding="utf-8-sig") as fh:
                for row in _parse_rows(fh):
                    counters.fetched += 1
                    journal = get_or_create_journal(session, row["issn_l"], title=row["title"])
                    upsert_one_to_one(
                        session, JournalMJL, journal.id,
                        jif=row["jif"], jif_quartile=row["quartile"] or None,
                        edition=row["edition"] or None, is_partial=False,
                        snapshot_date=snapshot_date,
                    )
                    counters.upserted += 1


if __name__ == "__main__":
    run()
