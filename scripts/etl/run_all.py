"""CLI orchestrator for the journal database ETL pipeline.

Usage:
    python scripts/etl/run_all.py --source all
    python scripts/etl/run_all.py --source annauniv,doaj,elsevier
    python scripts/etl/run_all.py --source doaj --dry-run

Runs each source's ingest script, then reconcile.py last (it depends on
every other source's output). This is the operational entry point for
both manual runs and future scheduling (cron/APScheduler) - documented
in the README, not built into this script.
"""
from __future__ import annotations

import argparse
import sys
import time

import ingest_annauniv_cfr
import ingest_cloudscraper_publishers
import ingest_doaj
import ingest_elsevier_apc
import ingest_frontiers_apc
import ingest_ieee_apc
import ingest_mjl_csv
import ingest_openalex_bulk
import ingest_openalex_citescore_estimate
import ingest_openalex_enrichment
import ingest_scimago
import ingest_scopus_source_list
import ingest_tf_sage_apc
import ingest_wiley_apc
import ingest_world_bank_income
import reconcile
import seed_publisher_waiver_policy
from src.db.engine import init_db

SOURCES = {
    "annauniv": ingest_annauniv_cfr.run,
    "doaj": lambda: ingest_doaj.run(live_check_limit=200),
    "scimago": ingest_scimago.run,
    "scopus": ingest_scopus_source_list.run,
    "mjl": ingest_mjl_csv.run,
    "elsevier": ingest_elsevier_apc.run,
    "wiley": ingest_wiley_apc.run,
    "ieee": ingest_ieee_apc.run,
    "frontiers": ingest_frontiers_apc.run,  # derives real slugs from DB (~219 journals), not the old 5-item stub
    "cloudscraper_publishers": ingest_cloudscraper_publishers.run,  # MDPI/ACM/OUP/PLOS
    "tf_sage": ingest_tf_sage_apc.run,  # real bulk sweep, see note in EXCLUDED_FROM_ALL below
    "worldbank": ingest_world_bank_income.run,
    "waiver_seed": seed_publisher_waiver_policy.run,
    "openalex_bulk": ingest_openalex_bulk.run,
    # Capped batch per run (same incremental-convergence pattern as the DOAJ
    # live-check above) - real Scopus CiteScore isn't reachable at all, this
    # backfills the honest OpenAlex-estimate substitute a few hundred
    # journals at a time across repeated scheduled runs.
    "openalex_citescore": lambda: ingest_openalex_citescore_estimate.run(limit=500),
    "openalex_enrichment": lambda: ingest_openalex_enrichment.run(limit=500),
    "reconcile": reconcile.run,
}

# Addressable by name (--source tf_sage) but excluded from the default "all"
# sweep: ingest_tf_sage_apc.run() is a real bulk sweep now, but the APC
# figure isn't actually reachable in either publisher's journal-page HTML
# yet (confirmed live, see ingest_tf_sage_apc.py's docstring) - running it
# under "all" would just log a wall of honest `failed` results for no
# benefit until that's resolved.
EXCLUDED_FROM_ALL = {"tf_sage"}

# Reconcile is the final default source because it depends on every ingest.


def main():
    parser = argparse.ArgumentParser(description="Run journal database ETL sources.")
    parser.add_argument("--source", default="all",
                         help="comma-separated source names, or 'all' (default)")
    parser.add_argument("--dry-run", action="store_true",
                         help="list what would run without executing")
    args = parser.parse_args()

    init_db()
    names = (
        [n for n in SOURCES if n not in EXCLUDED_FROM_ALL]
        if args.source == "all" else args.source.split(",")
    )
    if args.source != "all" and len(names) > 1 and "reconcile" not in names:
        names.append("reconcile")
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        print(f"Unknown source(s): {unknown}. Valid: {list(SOURCES.keys())}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("Would run, in order:", names)
        return

    for name in names:
        started = time.monotonic()
        try:
            SOURCES[name]()
        except Exception as exc:
            print(f"[{name}] FAILED: {exc}", file=sys.stderr)
        print(f"[{name}] took {time.monotonic() - started:.1f}s")

if __name__ == "__main__":
    main()
