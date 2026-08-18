"""Journal database blueprint: search/filter/detail API + ETL ops status,
and serves the built React micro-frontend (frontend-journals/dist) at
/journals.

Every response field carries its provenance (confidence: verified /
estimated / unknown, and which source table it came from) - same
philosophy as journal_metadata.py's provenance chain, now backed by SQL
instead of flat JSON.
"""
from __future__ import annotations

import os
import sys
import threading

from flask import Blueprint, jsonify, request, send_from_directory
from sqlalchemy import func, or_

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.db.engine import session_scope  # noqa: E402
from src.db.issn_utils import normalize_issn  # noqa: E402
from src.db.models import (  # noqa: E402
    ETLRunLog, Journal, JournalAnnaUnivCFR, JournalAPCConsolidated, JournalDOAJ,
    JournalMJL, JournalPublisherAPC, JournalRiskFlag, JournalScimago, JournalScopus,
)

journals_bp = Blueprint("journals", __name__)

_FRONTEND_DIST = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend-journals", "dist")
)


def _journal_summary(journal: Journal, apc, scimago, doaj, cfr) -> dict:
    return {
        "issn": journal.issn_l,
        "title": journal.title,
        "publisher": journal.publisher,
        "country": journal.country,
        "homepage_url": journal.homepage_url,
        "quartile": scimago.sjr_best_quartile if scimago else None,
        "quartile_source": "verified" if scimago else "unknown",
        "sjr": scimago.sjr_score if scimago else None,
        "h_index": scimago.h_index if scimago else None,
        "subject_category": scimago.subject_category if scimago else None,
        "in_doaj": bool(doaj and doaj.in_doaj),
        "apc_usd": apc.apc_usd if apc else None,
        "apc_source": apc.apc_source if apc else "unknown",
        "apc_confidence": apc.confidence if apc else "unknown",
        "waiver_available": apc.waiver_available if apc else None,
        "in_annauniv_cfr": bool(cfr and cfr.listed),
    }


@journals_bp.route("/api/journals")
def api_search_journals():
    search = (request.args.get("search") or "").strip()
    publisher = (request.args.get("publisher") or "").strip()
    quartile = (request.args.get("quartile") or "").strip()
    open_access = request.args.get("open_access")
    annauniv_cfr = request.args.get("annauniv_cfr")
    apc_max = request.args.get("apc_max", type=float)
    page = max(1, request.args.get("page", default=1, type=int))
    page_size = min(50, max(1, request.args.get("page_size", default=20, type=int)))
    sort = (request.args.get("sort") or "title").strip()

    with session_scope() as session:
        query = (
            session.query(Journal, JournalAPCConsolidated, JournalScimago, JournalDOAJ, JournalAnnaUnivCFR)
            .outerjoin(JournalAPCConsolidated, JournalAPCConsolidated.journal_id == Journal.id)
            .outerjoin(JournalScimago, JournalScimago.journal_id == Journal.id)
            .outerjoin(JournalDOAJ, JournalDOAJ.journal_id == Journal.id)
            .outerjoin(JournalAnnaUnivCFR, JournalAnnaUnivCFR.journal_id == Journal.id)
        )
        if search:
            like = f"%{search}%"
            query = query.filter(or_(Journal.title.ilike(like), Journal.issn_l.ilike(like)))
        if publisher:
            query = query.filter(Journal.publisher.ilike(f"%{publisher}%"))
        if quartile:
            query = query.filter(JournalScimago.sjr_best_quartile == quartile.upper())
        if open_access == "true":
            query = query.filter(JournalDOAJ.in_doaj.is_(True))
        if annauniv_cfr == "true":
            query = query.filter(JournalAnnaUnivCFR.listed.is_(True))
        if apc_max is not None:
            query = query.filter(JournalAPCConsolidated.apc_usd.isnot(None), JournalAPCConsolidated.apc_usd <= apc_max)

        if sort == "quartile":
            query = query.order_by(JournalScimago.sjr_best_quartile.asc().nullslast())
        elif sort == "apc":
            query = query.order_by(JournalAPCConsolidated.apc_usd.asc().nullslast())
        elif sort == "h_index":
            query = query.order_by(JournalScimago.h_index.desc().nullslast())
        else:
            query = query.order_by(Journal.title.asc())

        total = query.count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()

    return jsonify({
        "total": total, "page": page, "page_size": page_size,
        "results": [_journal_summary(j, apc, sci, doaj, cfr) for j, apc, sci, doaj, cfr in rows],
    })


@journals_bp.route("/api/journals/facets")
def api_facets():
    with session_scope() as session:
        publishers = [
            row[0] for row in
            session.query(Journal.publisher).filter(Journal.publisher.isnot(None))
            .group_by(Journal.publisher).order_by(func.count(Journal.id).desc()).limit(30).all()
        ]
        quartiles = [
            row[0] for row in
            session.query(JournalScimago.sjr_best_quartile).filter(JournalScimago.sjr_best_quartile.isnot(None))
            .distinct().order_by(JournalScimago.sjr_best_quartile).all()
        ]
    return jsonify({"publishers": publishers, "quartiles": quartiles})


@journals_bp.route("/api/journals/<issn>")
def api_journal_detail(issn: str):
    issn_l = normalize_issn(issn)
    if not issn_l:
        return jsonify({"error": "invalid ISSN"}), 400

    with session_scope() as session:
        journal = session.query(Journal).filter_by(issn_l=issn_l).one_or_none()
        if journal is None:
            return jsonify({"error": "not found"}), 404

        scimago = session.query(JournalScimago).filter_by(journal_id=journal.id).one_or_none()
        scopus = session.query(JournalScopus).filter_by(journal_id=journal.id).one_or_none()
        mjl = session.query(JournalMJL).filter_by(journal_id=journal.id).one_or_none()
        doaj = session.query(JournalDOAJ).filter_by(journal_id=journal.id).one_or_none()
        cfr = session.query(JournalAnnaUnivCFR).filter_by(journal_id=journal.id).one_or_none()
        apc = session.query(JournalAPCConsolidated).filter_by(journal_id=journal.id).one_or_none()
        publisher_apcs = session.query(JournalPublisherAPC).filter_by(journal_id=journal.id).all()
        risk_flags = session.query(JournalRiskFlag).filter_by(journal_id=journal.id).all()

        return jsonify({
            "issn": journal.issn_l, "title": journal.title,
            "publisher": journal.publisher, "country": journal.country,
            "homepage_url": journal.homepage_url,
            "scimago": {
                "sjr": scimago.sjr_score, "quartile": scimago.sjr_best_quartile,
                "h_index": scimago.h_index, "subject_category": scimago.subject_category,
                "coverage": scimago.coverage_years, "source_url": scimago.source_url,
                "snapshot_date": scimago.snapshot_date.isoformat() if scimago.snapshot_date else None,
            } if scimago else None,
            "scopus": {
                "citescore": scopus.citescore, "percentile": scopus.percentile,
                "asjc_codes": scopus.asjc_codes, "active_status": scopus.active_status,
            } if scopus else None,
            "mjl": {
                "jif": mjl.jif, "quartile": mjl.jif_quartile, "edition": mjl.edition,
                "is_partial": mjl.is_partial,
            } if mjl else None,
            "doaj": {
                "in_doaj": doaj.in_doaj, "has_apc": doaj.has_apc, "apc_amount": doaj.apc_amount,
                "apc_currency": doaj.apc_currency, "waiver_policy_text": doaj.waiver_policy_text,
                "waiver_policy_url": doaj.waiver_policy_url, "license_type": doaj.license_type,
                "live_checked_at": doaj.live_checked_at.isoformat() if doaj.live_checked_at else None,
                "diverged_from_csv": doaj.diverged_from_csv,
            } if doaj else None,
            "in_annauniv_cfr": bool(cfr and cfr.listed),
            "apc_consolidated": {
                "apc_usd": apc.apc_usd, "source": apc.apc_source, "confidence": apc.confidence,
                "waiver_available": apc.waiver_available, "waiver_notes": apc.waiver_notes,
            } if apc else None,
            "publisher_apcs": [
                {"publisher": p.publisher, "list_type": p.list_type, "apc_amount": p.apc_amount,
                 "currency": p.currency, "source_url": p.source_url}
                for p in publisher_apcs
            ],
            "risk_flags": [
                {"type": f.flag_type, "severity": f.severity, "reason": f.reason, "source": f.source}
                for f in risk_flags
            ],
        })


@journals_bp.route("/api/admin/etl/status")
def api_etl_status():
    with session_scope() as session:
        latest_ids = (
            session.query(ETLRunLog.source_name, func.max(ETLRunLog.id).label("max_id"))
            .group_by(ETLRunLog.source_name).subquery()
        )
        rows = (
            session.query(ETLRunLog)
            .join(latest_ids, ETLRunLog.id == latest_ids.c.max_id)
            .order_by(ETLRunLog.source_name)
            .all()
        )
        return jsonify([{
            "source": r.source_name, "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "fetched": r.records_fetched, "upserted": r.records_upserted, "failed": r.records_failed,
            "error": r.error_summary,
        } for r in rows])


_ETL_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "etl")


@journals_bp.route("/api/admin/etl/run/<source>", methods=["POST"])
def api_etl_run(source: str):
    def _run_in_background():
        if _ETL_SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, _ETL_SCRIPTS_DIR)
        import run_all
        if source not in run_all.SOURCES and source != "reconcile":
            return
        if source == "reconcile":
            import reconcile
            reconcile.run()
        else:
            run_all.SOURCES[source]()

    thread = threading.Thread(target=_run_in_background, daemon=True)
    thread.start()
    return jsonify({"status": "started", "source": source})


@journals_bp.route("/journals")
@journals_bp.route("/journals/<path:subpath>")
def serve_frontend(subpath: str = ""):
    index_path = os.path.join(_FRONTEND_DIST, "index.html")
    if not os.path.exists(index_path):
        return (
            "Journal database frontend not built yet. Run `npm install && npm run "
            "build` in frontend-journals/, or use the /api/journals/* endpoints "
            "directly.", 200,
        )
    return send_from_directory(_FRONTEND_DIST, "index.html")


@journals_bp.route("/journals/assets/<path:filename>")
def serve_frontend_assets(filename: str):
    return send_from_directory(os.path.join(_FRONTEND_DIST, "assets"), filename)
