"""Reconcile all ingested sources into journal_apc_consolidated and
journal_risk_flags per journal. Run after the source ingest scripts.

APC preference order (revised 2026-08-18 after a real discrepancy was
caught: Ain Shams Engineering Journal, ISSN 2090-4479, showed $1,500 from
DOAJ while Elsevier's own live price list says $1,800 - the old
DOAJ-always-wins rule was surfacing the less-authoritative figure):
  1. Same-publisher journal_publisher_apc match (via _publisher_key) -
     the publisher's own current stated price, most authoritative for
     what they actually charge.
  2. DOAJ (live-checked, then CSV) - primary for the majority of
     journals, which have no publisher-bulk list at all.
  3. Any other publisher's bulk row (rare - publisher transfer, etc).
  4. OpenAlex estimate retained from the bulk enrichment pass.
  5. unknown.
When #1 and #2 both exist and disagree by >10%, #1 still wins as
apc_usd, but the DOAJ figure is recorded in apc_discrepancy_notes so the
disagreement is visible, not silently erased. OpenAlex estimates remain
explicitly labelled and only fill the gap when no verified source exists.

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


def _differs_by_more_than_10_percent(reference, candidate) -> bool:
    return bool(
        reference
        and candidate
        and abs(candidate - reference) / reference > 0.10
    )


def _join_notes(*notes) -> str | None:
    return "\n".join(note for note in notes if note) or None


def _openalex_discrepancy_note(verified_amount, openalex_amount) -> str | None:
    if not _differs_by_more_than_10_percent(verified_amount, openalex_amount):
        return None
    return (
        f"OpenAlex estimates ${openalex_amount:,.0f} for this journal, differing "
        f"from the verified APC (${verified_amount:,.0f}) by more than 10%. "
        "Showing the verified figure as primary; verify at submission."
    )


def _prior_openalex_note(notes) -> str | None:
    if not notes:
        return None
    return next(
        (line for line in notes.splitlines() if line.startswith("OpenAlex estimates ")),
        None,
    )


def _consolidate_apc(journal_publisher: str, doaj, pub_apcs: list,
                     openalex_amount=None):
    priced = [p for p in pub_apcs if p.apc_amount is not None]
    doaj_amount = doaj.apc_amount if (doaj and doaj.has_apc and doaj.apc_amount) else None
    doaj_source = "doaj_live" if (doaj and doaj.live_checked_at) else "doaj_csv"

    publisher_key = _publisher_key(journal_publisher)
    same_pub = [p for p in priced if publisher_key and p.publisher == publisher_key]
    if same_pub:
        best = max(same_pub, key=lambda p: p.snapshot_date or 0)
        note = None
        if _differs_by_more_than_10_percent(best.apc_amount, doaj_amount):
            note = _join_notes(note, (
                f"DOAJ lists ${doaj_amount:,.0f} for this journal, differing from "
                f"{journal_publisher}'s own price list (${best.apc_amount:,.0f}) by more "
                f"than 10%. Showing the publisher's own figure as primary; DOAJ may "
                f"reflect an older or different tier - verify at submission."
            ))
        note = _join_notes(note, _openalex_discrepancy_note(best.apc_amount, openalex_amount))
        return best.apc_amount, f"publisher_bulk:{best.publisher}", "verified", note

    if doaj_amount:
        note = _openalex_discrepancy_note(doaj_amount, openalex_amount)
        return doaj_amount, doaj_source, "verified", note

    if priced:
        best = max(priced, key=lambda p: p.snapshot_date or 0)
        note = _openalex_discrepancy_note(best.apc_amount, openalex_amount)
        return best.apc_amount, f"publisher_bulk:{best.publisher}", "verified", note

    if openalex_amount:
        return openalex_amount, "openalex", "estimated", None

    return None, "unknown", "unknown", None


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

                consolidated = existing_consolidated.get(journal.id)
                openalex_amount = (
                    consolidated.apc_usd
                    if consolidated is not None
                    and consolidated.apc_source == "openalex"
                    and consolidated.confidence == "estimated"
                    else None
                )
                apc_usd, apc_source, confidence, discrepancy_note = _consolidate_apc(
                    journal.publisher, doaj, pub_apcs_by_journal.get(journal.id, []),
                    openalex_amount,
                )
                if openalex_amount is None:
                    discrepancy_note = _join_notes(
                        discrepancy_note,
                        _prior_openalex_note(
                            consolidated.apc_discrepancy_notes if consolidated else None
                        ),
                    )
                waiver_available, waiver_notes = _waiver_advisory(journal, policies_by_key)

                if consolidated is None:
                    consolidated = JournalAPCConsolidated(journal_id=journal.id)
                    session.add(consolidated)
                consolidated.apc_usd = apc_usd
                consolidated.apc_source = apc_source
                consolidated.confidence = confidence
                consolidated.apc_discrepancy_notes = discrepancy_note
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
