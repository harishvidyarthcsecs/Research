"""Shared helpers for every journal-database ETL script:
canonical-journal upsert, one-to-one source-table upsert, and the
etl_run_log context manager every ingest script wraps itself in.
"""
from __future__ import annotations

import datetime
import os
import sys
import time
from contextlib import contextmanager

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.db.engine import session_scope  # noqa: E402
from src.db.issn_utils import normalize_issn  # noqa: E402
from src.db.models import ETLRunLog, Journal, JournalIdentifier, JournalPublisherAPC  # noqa: E402


def get_or_create_journal(session, issn_l: str, title: str = "", publisher: str = "",
                           country: str = "", homepage_url: str = "") -> Journal:
    issn_l = normalize_issn(issn_l)
    if not issn_l:
        raise ValueError("cannot upsert a journal without a valid ISSN")
    journal = session.query(Journal).filter_by(issn_l=issn_l).one_or_none()
    if journal is None:
        # Also check the journal_identifiers alias table - a source keying
        # a journal by its online ISSN would otherwise miss a canonical row
        # another source already created under the print ISSN (or vice
        # versa), creating a duplicate. Confirmed live: this was exactly
        # how Wiley's ingest (single-ISSN lookup) split off a second row
        # for a journal CFR+Scimago had already merged correctly.
        ident = (
            session.query(JournalIdentifier)
            .filter((JournalIdentifier.issn_print == issn_l) | (JournalIdentifier.issn_online == issn_l))
            .first()
        )
        if ident is not None:
            journal = session.get(Journal, ident.journal_id)
    if journal is None:
        journal = Journal(issn_l=issn_l, title=title or issn_l, publisher=publisher,
                           country=country, homepage_url=homepage_url or None)
        session.add(journal)
        session.flush()
        return journal
    if homepage_url and not journal.homepage_url:
        journal.homepage_url = homepage_url
    if title and not journal.title:
        journal.title = title
    if publisher and not journal.publisher:
        journal.publisher = publisher
    if country and not journal.country:
        journal.country = country
    return journal


class IssnIndex:
    """In-memory issn -> Journal cache, built once per ingest script run.

    The naive version of this (a DB query per row, matching journals.issn_l
    OR journal_identifiers.issn_print/issn_online via an outer join) is an
    O(n^2)-ish pattern in SQLite - an OR condition spanning a joined table
    doesn't use the per-column indexes the way a single-column lookup does,
    so it gets slower as the table grows (confirmed live: still running
    after 4+ minutes on ~50k rows with climbing CPU, no completions). Same
    class of bug as the earlier reconcile.py N+1 fix - fixed the same way,
    by loading everything into a dict once and doing pure-Python lookups.
    """

    def __init__(self, session):
        self.session = session
        self._by_issn = {}
        for j in session.query(Journal.id, Journal.issn_l).all():
            self._by_issn[j.issn_l] = j.id
        for ident in session.query(JournalIdentifier).all():
            if ident.issn_print:
                self._by_issn.setdefault(ident.issn_print, ident.journal_id)
            if ident.issn_online:
                self._by_issn.setdefault(ident.issn_online, ident.journal_id)

    def resolve(self, issns: list, title: str = "", publisher: str = "",
                country: str = "", homepage_url: str = "") -> Journal:
        norm_issns = [normalize_issn(i) for i in issns if normalize_issn(i)]
        if not norm_issns:
            raise ValueError("cannot upsert a journal without at least one valid ISSN")

        journal_id = next((self._by_issn[i] for i in norm_issns if i in self._by_issn), None)
        journal = self.session.get(Journal, journal_id) if journal_id else None

        if journal is None:
            journal = Journal(issn_l=norm_issns[0], title=title or norm_issns[0],
                               publisher=publisher, country=country, homepage_url=homepage_url or None)
            self.session.add(journal)
            self.session.flush()
        else:
            if homepage_url and not journal.homepage_url:
                journal.homepage_url = homepage_url
            if title and not journal.title:
                journal.title = title
            if publisher and not journal.publisher:
                journal.publisher = publisher
            if country and not journal.country:
                journal.country = country

        for i in norm_issns:
            self._by_issn.setdefault(i, journal.id)

        identifiers = self.session.query(JournalIdentifier).filter_by(journal_id=journal.id).one_or_none()
        if identifiers is None:
            identifiers = JournalIdentifier(journal_id=journal.id)
            self.session.add(identifiers)
        if len(norm_issns) >= 1 and not identifiers.issn_print:
            identifiers.issn_print = norm_issns[0]
        if len(norm_issns) >= 2 and not identifiers.issn_online:
            identifiers.issn_online = norm_issns[1]

        return journal


def upsert_one_to_one(session, model_cls, journal_id: int, **fields):
    """Upsert a row on a table with a unique journal_id (Scimago/Scopus/MJL/DOAJ/CFR/consolidated)."""
    row = session.query(model_cls).filter_by(journal_id=journal_id).one_or_none()
    if row is None:
        row = model_cls(journal_id=journal_id, **fields)
        session.add(row)
    else:
        for key, value in fields.items():
            setattr(row, key, value)
    return row


def upsert_publisher_apc(session, journal_id: int, publisher: str, list_type: str = None, **fields):
    """Upsert on the real unique key (journal_id, publisher, list_type) -
    a journal can have multiple publisher-list rows (e.g. hybrid + fully-oa
    sister journal, or a publisher transfer), so this must not collapse
    to one row per journal like the 1:1 source tables do."""
    row = (
        session.query(JournalPublisherAPC)
        .filter_by(journal_id=journal_id, publisher=publisher, list_type=list_type)
        .one_or_none()
    )
    if row is None:
        row = JournalPublisherAPC(journal_id=journal_id, publisher=publisher, list_type=list_type, **fields)
        session.add(row)
    else:
        for key, value in fields.items():
            setattr(row, key, value)
    return row


class RateLimiter:
    """Simple fixed-delay limiter for polite per-record HTTP fetching."""

    def __init__(self, min_interval_s: float):
        self.min_interval_s = min_interval_s
        self._last = 0.0

    def wait(self):
        elapsed = time.monotonic() - self._last
        remaining = self.min_interval_s - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last = time.monotonic()


@contextmanager
def etl_run(source_name: str):
    """Wrap an ingest script's body; logs one etl_run_log row with counts.

    Usage:
        with etl_run("annauniv_cfr") as run:
            for row in rows:
                ...
                run.fetched += 1
                run.upserted += 1
    """
    class _Counters:
        fetched = 0
        upserted = 0
        failed = 0

    counters = _Counters()
    with session_scope() as log_session:
        log_row = ETLRunLog(source_name=source_name, status="running")
        log_session.add(log_row)
        log_session.flush()
        log_id = log_row.id

    error_summary = None
    status = "success"
    try:
        yield counters
    except Exception as exc:
        status = "failed"
        error_summary = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if counters.failed and status == "success":
            status = "partial"
        with session_scope() as log_session:
            log_row = log_session.get(ETLRunLog, log_id)
            log_row.finished_at = datetime.datetime.utcnow()
            log_row.records_fetched = counters.fetched
            log_row.records_upserted = counters.upserted
            log_row.records_failed = counters.failed
            log_row.status = status
            log_row.error_summary = error_summary
        print(f"[{source_name}] {status}: fetched={counters.fetched} "
              f"upserted={counters.upserted} failed={counters.failed}")
