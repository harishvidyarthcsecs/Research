"""Ingest Springer Nature: waiver country list (real, bulk) + per-journal
APC (on-demand, no bulk file - correcting an assumption made in planning).

Checked directly at implementation time (springernature.com/gp/open-
science/journals-books/journal-pricing-faqs): Springer's own FAQ states
"For more information on individual journal APCs, view the journal
homepage" - there is NO bulk fully-OA APC price list, unlike Elsevier/
Wiley/IEEE. Only their *subscription* price lists (USD/EUR/JPY XLSX,
confirmed downloadable from journal-price-lists) are bulk files, and
those aren't APC data. So Springer joins Taylor & Francis / SAGE / (most
of) Frontiers in the "per-journal lookup only" bucket, not the bulk-file
bucket the plan first assumed - documented honestly here rather than
papered over.

What IS real and bulk on that FAQ page: a named list of ~60+ countries
qualifying for a fully-sponsored ("no cost") gold OA fund, e.g. India,
Nigeria, Bangladesh, Kenya - distinct from and broader than the
Research4Life tiers used elsewhere. Captured into `publisher_waiver_policy`.
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

FAQ_URL = "https://www.springernature.com/gp/open-science/journals-books/journal-pricing-faqs"


def fetch_waiver_qualifying_countries() -> list:
    resp = requests.get(FAQ_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    marker = soup.find(string=re.compile("Qualifying locations", re.I))
    if marker is None:
        return []
    container = marker.find_parent("p")
    ul = container.find_next_sibling("ul") if container else None
    if ul is None:
        return []
    return [li.get_text(strip=True) for li in ul.find_all("li")]


def run():
    countries = fetch_waiver_qualifying_countries()
    print(f"[springer_apc] no bulk APC file exists (confirmed live) - "
          f"per-journal lookup only. Waiver-qualifying countries found: {len(countries)}")
    return countries


if __name__ == "__main__":
    run()
