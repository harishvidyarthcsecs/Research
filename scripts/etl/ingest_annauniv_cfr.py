"""Ingest Anna University CFR's PhD-scholar-approved journal list.

Source: https://cfr.annauniv.edu/research/academics/journals-list.php
Public university page, static HTML table (~12,200 rows: Sl.No, Full
Journal Title, Print-ISSN, E-ISSN, Publisher, Country). No login.

The site's TLS certificate chain is broken (verified directly:
`unable to verify the first certificate`) - this is their own
misconfigured chain, not a MITM signal. We try normal verification
first and only fall back to a relaxed context for this one host,
logging a warning each time, rather than disabling verification
globally.
"""
from __future__ import annotations

import datetime
import warnings

import requests
import urllib3
from bs4 import BeautifulSoup

from common import IssnIndex, etl_run, upsert_one_to_one
from src.db.engine import session_scope
from src.db.issn_utils import normalize_issn
from src.db.models import JournalAnnaUnivCFR

URL = "https://cfr.annauniv.edu/research/academics/journals-list.php"


def _fetch_html() -> str:
    try:
        resp = requests.get(URL, timeout=30)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.SSLError:
        warnings.warn(
            f"{URL} has a broken TLS certificate chain (server-side "
            "misconfiguration, confirmed by direct inspection) - retrying "
            "this one host with certificate verification disabled.",
            stacklevel=2,
        )
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = requests.get(URL, timeout=30, verify=False)
        resp.raise_for_status()
        return resp.text


def _parse_rows(html: str):
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="example")
    if table is None:
        return
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) != 6:
            continue
        sl_no, title, issn_print, issn_online, publisher, country = cells
        if not sl_no.isdigit():
            continue
        yield {
            "sl_no": int(sl_no),
            "title": title,
            "issn_print": normalize_issn(issn_print),
            "issn_online": normalize_issn(issn_online),
            "publisher": publisher,
            "country": country,
        }


def run():
    html = _fetch_html()
    snapshot_date = datetime.datetime.utcnow()

    with etl_run("annauniv_cfr") as counters:
        with session_scope() as session:
            index = IssnIndex(session)
            for row in _parse_rows(html):
                counters.fetched += 1
                issns = [row["issn_print"], row["issn_online"]]
                if not any(issns):
                    counters.failed += 1
                    continue
                journal = index.resolve(
                    issns, title=row["title"],
                    publisher=row["publisher"], country=row["country"],
                )
                upsert_one_to_one(
                    session, JournalAnnaUnivCFR, journal.id,
                    listed=True, sl_no=row["sl_no"], snapshot_date=snapshot_date,
                )
                counters.upserted += 1


if __name__ == "__main__":
    run()
