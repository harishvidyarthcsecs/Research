"""
Journal facts with provenance: quartile, indexing, APC, predatory risk.

Every value this module returns carries a source label, because the honest
answer to "is this Q1?" is often "we don't know" — and a tool that decides where
someone submits their paper must say so rather than guess.

Resolution order for the quartile:

  1. Scimago verified lookup (src/data/scimago_verified.json)    → authoritative
  2. OpenAlex field percentile (src/data/journal_baselines.json) → estimate
  3. Unknown                                                     → say so

The LLM is deliberately not in that chain. It used to be, and it invented
quartiles for journals it had never seen.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

import requests

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Publishers repeatedly named in predatory-publishing studies and in the
# archived Beall's List. Presence here is a prompt to check, never a verdict —
# Beall's List has not been updated since January 2017.
_HIGH_RISK_PUBLISHERS = {
    "omics", "omics international", "omics publishing group",
    "scientific research publishing", "scirp",
    "academic journals", "academic journals inc",
    "science publishing group", "sciencepg",
    "world academy of science engineering and technology", "waset",
    "bentham open", "insight medical publishing",
    "auctores", "longdom", "hilaris", "iomc", "pulsus group",
}

# An unusually cheap APC is a classic predatory tell: real peer review costs
# money. Legitimate journals in the global south do publish below this, so the
# flag is advisory.
_SUSPICIOUS_APC_USD = 150


def _load(filename: str) -> dict:
    try:
        with open(os.path.join(_DATA_DIR, filename)) as fh:
            return json.load(fh)
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _baselines() -> dict:
    return _load("journal_baselines.json")


def _db_scimago_lookup(issns: list) -> Optional[dict]:
    """Verified Scimago quartile from the SQL journal database (replaces the
    old scimago_verified.json read)."""
    from src.db.engine import session_scope
    from src.db.models import Journal, JournalScimago

    with session_scope() as session:
        row = (
            session.query(JournalScimago, Journal)
            .join(Journal, Journal.id == JournalScimago.journal_id)
            .filter(Journal.issn_l.in_(issns))
            .first()
        )
        if row is None:
            return None
        scimago, journal = row
        if scimago.sjr_best_quartile not in ("Q1", "Q2", "Q3", "Q4"):
            return None
        return {
            "q": scimago.sjr_best_quartile, "field": scimago.subject_category or "",
            "title": journal.title, "h_index": scimago.h_index,
        }


def _db_journal_facts(issns: list) -> dict:
    """Name/publisher/APC/DOAJ facts from the SQL journal database (replaces
    the old journal_index.json read). Empty dict if the journal isn't in
    our database yet."""
    from src.db.engine import session_scope
    from src.db.models import Journal, JournalAPCConsolidated, JournalDOAJ, JournalScimago

    with session_scope() as session:
        journal = session.query(Journal).filter(Journal.issn_l.in_(issns)).first()
        if journal is None:
            return {}
        doaj = session.query(JournalDOAJ).filter_by(journal_id=journal.id).one_or_none()
        apc = session.query(JournalAPCConsolidated).filter_by(journal_id=journal.id).one_or_none()
        scimago = session.query(JournalScimago).filter_by(journal_id=journal.id).one_or_none()
        return {
            "name": journal.title, "publisher": journal.publisher,
            "h_index": scimago.h_index if scimago else None,
            "is_oa": bool(doaj and doaj.in_doaj), "in_doaj": bool(doaj and doaj.in_doaj),
            "apc_usd": apc.apc_usd if apc else None,
        }


def data_status() -> dict:
    """What reference data is actually loaded — surfaced in the UI."""
    from src.db.engine import session_scope
    from src.db.models import Journal, JournalScimago

    baselines = _baselines()
    with session_scope() as session:
        scimago_verified = session.query(JournalScimago).count()
        indexed_issns = session.query(Journal).count()
    return {
        "scimago_verified": scimago_verified,
        "indexed_issns": indexed_issns,
        "baseline_fields": len(baselines.get("fields", {})),
        "baseline_generated_at": baselines.get("generated_at"),
        "baseline_sample_size": baselines.get("sample_size"),
    }


def _normalize(issn: Optional[str]) -> str:
    """OpenAlex and CrossRef both emit hyphenated ISSNs; Scimago does not."""
    issn = (issn or "").strip().upper()
    if len(issn) == 8 and "-" not in issn:
        return f"{issn[:4]}-{issn[4:]}"
    return issn


def _all_issns(issn_l: Optional[str], issn_list: Optional[list]) -> list:
    seen, out = set(), []
    for raw in [issn_l] + list(issn_list or []):
        norm = _normalize(raw)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _dominant_field(source: dict) -> str:
    """Field the journal publishes in most, from its OpenAlex topics."""
    counts: dict = {}
    for topic in source.get("topics") or []:
        name = (topic.get("field") or {}).get("display_name", "")
        if name:
            counts[name] = counts.get(name, 0) + 1
    return max(counts, key=counts.get) if counts else ""


def _verified_quartile(issns: list) -> Optional[dict]:
    record = _db_scimago_lookup(issns)
    if record is None:
        return None
    return {
        "quartile": record["q"],
        "quartile_source": "verified",
        "quartile_source_label": "Scimago (verified)",
        "quartile_field": record.get("field", ""),
    }


def _estimated_quartile(citedness: float, field: str) -> dict:
    """Place a journal in a band using measured citation rates for its field."""
    baselines = _baselines()
    field_cutoffs = (baselines.get("fields") or {}).get(field)
    cutoffs = field_cutoffs or baselines.get("global")

    if not cutoffs or not citedness:
        return {
            "quartile": "?",
            "quartile_source": "unknown",
            "quartile_source_label": "Not available",
            "quartile_field": field,
        }

    if citedness >= cutoffs["q1_cutoff"]:
        band = "Q1"
    elif citedness >= cutoffs["q2_cutoff"]:
        band = "Q2"
    elif citedness >= cutoffs["q3_cutoff"]:
        band = "Q3"
    else:
        band = "Q4"

    scope = field if field_cutoffs else "all fields"
    return {
        "quartile": band,
        "quartile_source": "estimated",
        "quartile_source_label": f"OpenAlex citation percentile — {scope}, not Scimago",
        "quartile_field": field,
    }


def _predatory_flags(record: dict, in_doaj: bool, apc_usd, is_oa: bool) -> list:
    """Advisory warnings, each carrying the reason that triggered it."""
    flags = []
    publisher = (record.get("publisher") or "").lower()

    if any(risky in publisher for risky in _HIGH_RISK_PUBLISHERS):
        flags.append({
            "level": "high",
            "reason": f"Publisher '{record.get('publisher')}' appears in predatory-publishing "
                      "literature. Verify independently before submitting.",
        })

    if is_oa and not in_doaj:
        flags.append({
            "level": "medium",
            "reason": "Open access but not listed in DOAJ. DOAJ vets OA journals, "
                      "so absence is worth checking.",
        })

    if apc_usd is not None and 0 < apc_usd < _SUSPICIOUS_APC_USD:
        flags.append({
            "level": "low",
            "reason": f"Unusually low APC (${apc_usd}). Real peer review is expensive; "
                      "confirm the review process is genuine.",
        })

    if (record.get("works") or 0) > 20000 and (record.get("h_index") or 0) < 30:
        flags.append({
            "level": "medium",
            "reason": "Very high publication volume with low citation impact — "
                      "a pattern seen in low-selectivity venues.",
        })

    return flags


def fetch_doaj(issns: list, timeout: int = 8) -> dict:
    """DOAJ facts: APC, licence, review process. Empty dict if unlisted."""
    for issn in issns[:2]:
        try:
            resp = requests.get(
                f"https://doaj.org/api/search/journals/issn:{issn}",
                timeout=timeout,
            )
            if resp.status_code != 200:
                continue
            results = resp.json().get("results") or []
            if not results:
                continue

            bib = results[0].get("bibjson") or {}
            apc = bib.get("apc") or {}
            prices = apc.get("max") or []
            return {
                "in_doaj": True,
                "doaj_apc": prices[0] if prices else None,
                "doaj_has_apc": apc.get("has_apc"),
                "licences": [lic.get("type") for lic in (bib.get("license") or [])],
                "review_process": (bib.get("editorial") or {}).get("review_process") or [],
            }
        except Exception:
            continue
    return {}


def resolve_journal(openalex_source: dict, with_doaj: bool = False) -> dict:
    """Turn one OpenAlex source record into journal facts with provenance.

    Args:
        openalex_source: a record from the OpenAlex /sources endpoint.
        with_doaj: also call the DOAJ API for licence and review-process detail.
            Off by default — it costs one HTTP request per journal.
    """
    issns = _all_issns(openalex_source.get("issn_l"), openalex_source.get("issn"))
    stats = openalex_source.get("summary_stats") or {}

    # The SQL journal database is authoritative for anything it covers; fall
    # back to whatever the live OpenAlex API response carried.
    indexed = _db_journal_facts(issns)

    field = indexed.get("field") or _dominant_field(openalex_source)
    citedness = indexed.get("citedness") or stats.get("2yr_mean_citedness") or 0.0
    in_doaj = indexed.get("in_doaj", openalex_source.get("is_in_doaj", False))
    is_oa = indexed.get("is_oa", openalex_source.get("is_oa", False))
    apc_usd = indexed.get("apc_usd", openalex_source.get("apc_usd"))

    record = {
        "name": openalex_source.get("display_name") or indexed.get("name", ""),
        "issn": issns[0] if issns else "",
        "publisher": (openalex_source.get("host_organization_name")
                      or indexed.get("publisher", "")),
        "field": field,
        "citedness": round(float(citedness), 2),
        "h_index": indexed.get("h_index") or stats.get("h_index") or 0,
        "works": indexed.get("works") or openalex_source.get("works_count") or 0,
        "is_oa": is_oa,
        "in_doaj": in_doaj,
        "apc_usd": apc_usd,
        "in_reference_index": bool(indexed),
    }

    record.update(_verified_quartile(issns)
                  or _estimated_quartile(record["citedness"], field))

    if with_doaj and issns:
        record.update(fetch_doaj(issns))
        in_doaj = record.get("in_doaj", in_doaj)

    record["risk_flags"] = _predatory_flags(record, in_doaj, apc_usd, is_oa)
    return record
