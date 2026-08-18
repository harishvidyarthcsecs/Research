"""Reconcile all ingested sources into journal_apc_consolidated and
journal_risk_flags per journal. Run after the source ingest scripts.

APC preference order (per plan): DOAJ live/CSV -> publisher bulk list ->
unknown. (OpenAlex-estimate is still owned by journal_metadata.py's
legacy JSON path until that module is swapped to read this DB - not
duplicated here to avoid two sources of truth mid-migration.)

Risk flags port journal_metadata.py::_predatory_flags to be DB-driven:
same high-risk publisher list, same OA-not-in-DOAJ check, same
suspiciously-low-APC threshold. Volume/impact-mismatch flag is skipped
here (works_count isn't in this schema yet - it lives in the legacy
OpenAlex-backed journal_index.json) rather than guessed from partial data.
"""
from __future__ import annotations

from common import etl_run
from src.db.engine import session_scope
from src.db.models import (
    Journal, JournalAPCConsolidated, JournalDOAJ, JournalPublisherAPC,
    JournalRiskFlag, PublisherWaiverPolicy,
)

_HIGH_RISK_PUBLISHERS = {
    "omics", "omics international", "omics publishing group",
    "scientific research publishing", "scirp",
    "academic journals", "academic journals inc",
    "science publishing group", "sciencepg",
    "world academy of science engineering and technology", "waset",
    "bentham open", "insight medical publishing",
    "auctores", "longdom", "hilaris", "iomc", "pulsus group",
}
_SUSPICIOUS_APC_USD = 150

_PUBLISHER_KEY_MAP = {
    "elsevier": "elsevier", "wiley": "wiley", "john wiley": "wiley",
    "springer": "springer", "sage": "sage",
    "association for computing machinery": "acm", "ieee": "ieee",
    "frontiers": "frontiers", "mdpi": "mdpi", "oxford university press": "oup",
    "taylor": "tandf", "public library of science": "plos",
}


def _publisher_key(publisher_name: str) -> str:
    name = (publisher_name or "").lower()
    for needle, key in _PUBLISHER_KEY_MAP.items():
        if needle in name:
            return key
    return ""


def _consolidate_apc(doaj, pub_apcs: list):
    if doaj and doaj.has_apc and doaj.apc_amount:
        source = "doaj_live" if doaj.live_checked_at else "doaj_csv"
        return doaj.apc_amount, source, "verified"

    priced = [p for p in pub_apcs if p.apc_amount is not None]
    if priced:
        best = max(priced, key=lambda p: p.snapshot_date or 0)
        return best.apc_amount, f"publisher_bulk:{best.publisher}", "verified"

    return None, "unknown", "unknown"


def _waiver_advisory(journal: Journal, policies_by_key: dict):
    key = _publisher_key(journal.publisher)
    policy = policies_by_key.get(key)
    if policy is None:
        return None, None
    notes = (
        f"{journal.publisher} states a waiver policy (type: {policy.policy_type}). "
        f"Full waiver typically for: {policy.full_waiver_income_groups or 'see policy'}; "
        f"discount typically for: {policy.discount_income_groups or 'see policy'}"
        + (f" ({policy.discount_pct:.0f}%)" if policy.discount_pct else "")
        + f". Verify at submission: {policy.policy_url}"
    )
    return True, notes


def _risk_flags(journal: Journal, apc_usd, in_doaj: bool, is_oa: bool):
    flags = []
    publisher = (journal.publisher or "").lower()
    if any(risky in publisher for risky in _HIGH_RISK_PUBLISHERS):
        flags.append(("predatory_publisher", "high",
                       f"Publisher '{journal.publisher}' appears in predatory-publishing "
                       "literature. Verify independently before submitting.",
                       "Beall's List / predatory-publishing literature (archived, frozen Jan 2017)"))
    if is_oa and not in_doaj:
        flags.append(("oa_not_in_doaj", "medium",
                       "Open access but not listed in DOAJ. DOAJ vets OA journals, "
                       "so absence is worth checking.", "DOAJ cross-reference"))
    if apc_usd is not None and 0 < apc_usd < _SUSPICIOUS_APC_USD:
        flags.append(("suspicious_apc", "low",
                       f"Unusually low APC (${apc_usd:.0f}). Real peer review is expensive; "
                       "confirm the review process is genuine.", "APC threshold heuristic"))
    return flags


def run():
    with etl_run("reconcile") as counters:
        with session_scope() as session:
            journals = session.query(Journal).all()

            doaj_by_journal = {d.journal_id: d for d in session.query(JournalDOAJ).all()}
            pub_apcs_by_journal = {}
            for row in session.query(JournalPublisherAPC).all():
                pub_apcs_by_journal.setdefault(row.journal_id, []).append(row)
            policies_by_key = {p.publisher: p for p in session.query(PublisherWaiverPolicy).all()}
            existing_consolidated = {
                c.journal_id: c for c in session.query(JournalAPCConsolidated).all()
            }

            # Bulk-clear old risk flags once instead of per-journal deletes.
            session.query(JournalRiskFlag).delete()

            new_flags = []
            for journal in journals:
                counters.fetched += 1
                doaj = doaj_by_journal.get(journal.id)
                in_doaj = bool(doaj and doaj.in_doaj)
                is_oa = in_doaj  # our schema's only direct OA signal today is DOAJ listing

                apc_usd, apc_source, confidence = _consolidate_apc(doaj, pub_apcs_by_journal.get(journal.id, []))
                waiver_available, waiver_notes = _waiver_advisory(journal, policies_by_key)

                consolidated = existing_consolidated.get(journal.id)
                if consolidated is None:
                    consolidated = JournalAPCConsolidated(journal_id=journal.id)
                    session.add(consolidated)
                consolidated.apc_usd = apc_usd
                consolidated.apc_source = apc_source
                consolidated.confidence = confidence
                consolidated.waiver_available = waiver_available
                consolidated.waiver_notes = waiver_notes

                for flag_type, severity, reason, source in _risk_flags(journal, apc_usd, in_doaj, is_oa):
                    new_flags.append(JournalRiskFlag(
                        journal_id=journal.id, flag_type=flag_type,
                        severity=severity, reason=reason, source=source,
                    ))
                counters.upserted += 1

            session.add_all(new_flags)


if __name__ == "__main__":
    run()
