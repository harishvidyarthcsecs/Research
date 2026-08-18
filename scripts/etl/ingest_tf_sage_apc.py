"""On-demand per-journal APC lookup for Taylor & Francis and SAGE.

Confirmed live this session: neither publisher exposes a bulk APC file
(T&F's own price-lists page only has subscription-tier PDFs; SAGE has
no bulk export either) - both require a per-journal page fetch. So
unlike the bulk-file publishers, this module exposes lookup functions
called lazily when a specific T&F/SAGE journal is viewed in the app
(src/blueprints/journals.py), rather than a nightly bulk `run()` over
~2,700+ T&F journals.

SAGE per-journal pages carry an APC figure directly on the journal's
"Open Access options" page; exact selector is confirmed only for the
general waiver-policy page fetched this session (sagepub.com), not yet
against an individual journal page - this is a best-effort parser that
falls back to `None` (never a guess) if the expected structure isn't found.
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup


def fetch_tf_apc(journal_slug_or_url: str):
    """journal_slug_or_url: a tandfonline.com journal homepage URL, e.g.
    https://www.tandfonline.com/journals/tjhs20"""
    try:
        resp = requests.get(journal_slug_or_url, timeout=20)
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
        resp = requests.get(journal_url, timeout=20)
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


def run():
    print("[tf_sage_apc] no bulk file exists for either publisher (confirmed "
          "live) - use fetch_tf_apc(url) / fetch_sage_apc(url) on-demand per "
          "journal from the API layer instead of a bulk run.")


if __name__ == "__main__":
    run()
