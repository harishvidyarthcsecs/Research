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
    "frontiers": ingest_frontiers_apc.run,
    "cloudscraper_publishers": ingest_cloudscraper_publishers.run,  # MDPI/ACM/OUP/PLOS
    "tf_sage": ingest_tf_sage_apc.run,  # prints guidance only, on-demand elsewhere
    "worldbank": ingest_world_bank_income.run,
    "waiver_seed": seed_publisher_waiver_policy.run,
}
# reconcile always runs last, separately - it depends on every other source.


def main():
    parser = argparse.ArgumentParser(description="Run journal database ETL sources.")
    parser.add_argument("--source", default="all",
                         help="comma-separated source names, or 'all' (default)")
    parser.add_argument("--dry-run", action="store_true",
                         help="list what would run without executing")
    args = parser.parse_args()

    init_db()
    names = list(SOURCES.keys()) if args.source == "all" else args.source.split(",")
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        print(f"Unknown source(s): {unknown}. Valid: {list(SOURCES.keys())}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("Would run, in order:", names, "then reconcile")
        return

    for name in names:
        started = time.monotonic()
        try:
            SOURCES[name]()
        except Exception as exc:
            print(f"[{name}] FAILED: {exc}", file=sys.stderr)
        print(f"[{name}] took {time.monotonic() - started:.1f}s")

    if args.source == "all" or len(names) > 1:
        reconcile.run()


if __name__ == "__main__":
    main()
