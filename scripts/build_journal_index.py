"""
Build the offline journal index and per-field quartile baselines.

Why this exists: the recommender used to ask an LLM what a journal's Scimago
quartile was. That is a hallucination surface on the one number that decides
where someone submits their paper. This script replaces the guess with measured
data.

Two outputs, both written to src/data/:

  journal_baselines.json  per-field cutoffs of OpenAlex 2-year mean citedness,
                          used to place any journal in a quartile band
  journal_index.json      per-ISSN facts (field, citedness, h-index, DOAJ
                          membership, APC) so lookups need no network call

Scimago's own CSV is behind Cloudflare and cannot be fetched automatically. If
you download it by hand from https://www.scimagojr.com/journalrank.php
("Download data") and save it as data/scimago_raw.csv, this script merges its
real quartiles into src/data/scimago_verified.json, which always outranks the
OpenAlex estimate at lookup time.

Usage:
    python scripts/build_journal_index.py                # default 8000 journals
    python scripts/build_journal_index.py --limit 20000  # wider, slower
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "src" / "data"
SCIMAGO_RAW = ROOT / "data" / "scimago_raw.csv"
SCIMAGO_VERIFIED = DATA_DIR / "scimago_verified.json"
BASELINES_OUT = DATA_DIR / "journal_baselines.json"
INDEX_OUT = DATA_DIR / "journal_index.json"

OPENALEX = "https://api.openalex.org/sources"
# OpenAlex asks for a contact address; it buys a faster rate-limit pool.
MAILTO = os.environ.get("OPENALEX_MAILTO", "research@example.com")

SELECT = ",".join([
    "id", "display_name", "issn_l", "issn", "summary_stats", "topics",
    "is_in_doaj", "is_oa", "apc_usd", "host_organization_name", "works_count",
])

# Fields with fewer journals than this fall back to the global cutoffs — a
# quartile computed from a handful of journals is noise.
MIN_FIELD_SAMPLE = 40


def fetch_journals(limit: int) -> list:
    """Page through the most-published journals on OpenAlex."""
    journals: list = []
    cursor = "*"
    session = requests.Session()

    while len(journals) < limit:
        resp = session.get(OPENALEX, params={
            "filter": "type:journal",
            "select": SELECT,
            "sort": "works_count:desc",
            "per-page": 200,
            "cursor": cursor,
            "mailto": MAILTO,
        }, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        batch = payload.get("results", [])
        if not batch:
            break
        journals.extend(batch)

        cursor = (payload.get("meta") or {}).get("next_cursor")
        if not cursor:
            break

        print(f"  fetched {len(journals)}", end="\r", flush=True)
        time.sleep(0.15)

    print(f"  fetched {len(journals)} journals" + " " * 12)
    return journals[:limit]


def dominant_field(journal: dict) -> str:
    """The field the journal publishes in most, per its OpenAlex topics."""
    counts = Counter(
        (t.get("field") or {}).get("display_name", "")
        for t in (journal.get("topics") or [])
    )
    counts.pop("", None)
    return counts.most_common(1)[0][0] if counts else ""


def citedness(journal: dict) -> float:
    return (journal.get("summary_stats") or {}).get("2yr_mean_citedness") or 0.0


def _cutoffs(scores: list) -> dict:
    """Quartile boundaries for one field's citation rates."""
    scores = sorted(scores)
    quarters = statistics.quantiles(scores, n=4)
    return {
        # Q1 starts at the 75th percentile: the top quarter by citation rate.
        "q1_cutoff": round(quarters[2], 4),
        "q2_cutoff": round(quarters[1], 4),
        "q3_cutoff": round(quarters[0], 4),
        "n": len(scores),
    }


def build_baselines(journals: list) -> dict:
    """Quartile cutoffs of 2-year mean citedness, per field."""
    by_field: dict = defaultdict(list)
    for j in journals:
        field = dominant_field(j)
        if field:
            by_field[field].append(citedness(j))

    fields = {
        field: _cutoffs(scores)
        for field, scores in by_field.items()
        if len(scores) >= MIN_FIELD_SAMPLE
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "OpenAlex 2yr_mean_citedness percentiles",
        "sample_size": len(journals),
        "min_field_sample": MIN_FIELD_SAMPLE,
        "note": (
            "Cutoffs come from the most-published journals per field, so they "
            "skew higher than Scimago's, which covers every indexed journal. "
            "Treat the resulting band as an estimate, never as a Scimago quartile."
        ),
        "global": _cutoffs([citedness(j) for j in journals]),
        "fields": fields,
    }


def build_index(journals: list) -> dict:
    """Per-ISSN facts, so a lookup costs no network call."""
    index: dict = {}
    for j in journals:
        stats = j.get("summary_stats") or {}
        record = {
            "name": j.get("display_name", ""),
            "field": dominant_field(j),
            "citedness": round(citedness(j), 4),
            "h_index": stats.get("h_index") or 0,
            "in_doaj": bool(j.get("is_in_doaj")),
            "is_oa": bool(j.get("is_oa")),
            "apc_usd": j.get("apc_usd"),
            "publisher": j.get("host_organization_name") or "",
            "works": j.get("works_count") or 0,
        }
        # Index under every ISSN the journal carries — callers may hold either.
        for issn in filter(None, [j.get("issn_l")] + (j.get("issn") or [])):
            index.setdefault(issn.strip(), record)
    return index


def merge_scimago_csv() -> int:
    """Fold a manually downloaded Scimago CSV into the verified lookup."""
    if not SCIMAGO_RAW.exists():
        return 0

    try:
        existing = json.loads(SCIMAGO_VERIFIED.read_text())
    except Exception:
        existing = {}

    added = 0
    with SCIMAGO_RAW.open(newline="", encoding="utf-8-sig") as fh:
        # Scimago exports semicolon-separated.
        for row in csv.DictReader(fh, delimiter=";"):
            quartile = (row.get("SJR Best Quartile") or "").strip()
            if quartile not in ("Q1", "Q2", "Q3", "Q4"):
                continue

            # Scimago writes categories as "Hematology (Q1); Oncology (Q1)" —
            # keep the first category name, drop its quartile marker.
            categories = (row.get("Categories") or "").split(";")[0].strip()
            categories = re.sub(r"\s*\(Q[1-4]\)\s*$", "", categories)
            for issn in (row.get("Issn") or "").split(","):
                issn = issn.strip()
                if len(issn) != 8:
                    continue
                # Scimago prints ISSNs unhyphenated; the rest of the app uses
                # the hyphenated form OpenAlex and CrossRef return.
                formatted = f"{issn[:4]}-{issn[4:]}"
                existing[formatted] = {
                    "q": quartile,
                    "field": categories,
                    "title": (row.get("Title") or "").strip(),
                    "source": "Scimago CSV",
                }
                added += 1

    SCIMAGO_VERIFIED.write_text(json.dumps(existing, indent=2, sort_keys=True))
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description="Build journal index and baselines")
    parser.add_argument("--limit", type=int, default=8000,
                        help="how many journals to sample from OpenAlex")
    parser.add_argument("--merge-only", action="store_true",
                        help="only ingest data/scimago_raw.csv; skip the OpenAlex fetch")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.merge_only:
        merged = merge_scimago_csv()
        if not merged:
            print(f"Nothing merged — is {SCIMAGO_RAW.relative_to(ROOT)} present?",
                  file=sys.stderr)
            return 1
        print(f"Merged {merged} verified quartiles from {SCIMAGO_RAW.name}")
        return 0

    print(f"Fetching up to {args.limit} journals from OpenAlex...")
    journals = fetch_journals(args.limit)
    if not journals:
        print("No journals returned — is OpenAlex reachable?", file=sys.stderr)
        return 1

    baselines = build_baselines(journals)
    BASELINES_OUT.write_text(json.dumps(baselines, indent=2))
    print(f"Wrote {BASELINES_OUT.relative_to(ROOT)} "
          f"({len(baselines['fields'])} fields)")

    index = build_index(journals)
    INDEX_OUT.write_text(json.dumps(index, indent=2, sort_keys=True))
    print(f"Wrote {INDEX_OUT.relative_to(ROOT)} ({len(index)} ISSNs)")

    merged = merge_scimago_csv()
    if merged:
        print(f"Merged {merged} verified quartiles from {SCIMAGO_RAW.name}")
    else:
        print(f"No {SCIMAGO_RAW.relative_to(ROOT)} found — "
              "download it from scimagojr.com to add verified quartiles")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
