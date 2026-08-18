"""SQLAlchemy ORM models for the journal database.

Replaces the old flat-JSON reference data (src/data/*.json) with a real
SQL schema. One table per source (Scimago, Scopus, MJL, DOAJ, Anna
University CFR, per-publisher APC lists), joined on ISSN through the
canonical `journals` row. Every source table carries its own
snapshot_date/source_url so provenance is a column, not a guess -
continuing the verified/estimated/unknown philosophy already established
in journal_metadata.py.
"""
from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


class Journal(Base):
    """Canonical journal row. One per ISSN-L family."""
    __tablename__ = "journals"

    id = Column(Integer, primary_key=True)
    issn_l = Column(String(9), unique=True, index=True, nullable=False)
    title = Column(String(500), nullable=False)
    publisher = Column(String(300))
    country = Column(String(100))
    homepage_url = Column(String(500))
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    identifiers = relationship("JournalIdentifier", back_populates="journal", uselist=False)
    scimago = relationship("JournalScimago", back_populates="journal", uselist=False)
    scopus = relationship("JournalScopus", back_populates="journal", uselist=False)
    mjl = relationship("JournalMJL", back_populates="journal", uselist=False)
    doaj = relationship("JournalDOAJ", back_populates="journal", uselist=False)
    annauniv_cfr = relationship("JournalAnnaUnivCFR", back_populates="journal", uselist=False)
    publisher_apcs = relationship("JournalPublisherAPC", back_populates="journal")
    apc_consolidated = relationship("JournalAPCConsolidated", back_populates="journal", uselist=False)
    risk_flags = relationship("JournalRiskFlag", back_populates="journal")


class JournalIdentifier(Base):
    __tablename__ = "journal_identifiers"

    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.id"), unique=True, nullable=False)
    issn_print = Column(String(9), index=True)
    issn_online = Column(String(9), index=True)
    scopus_source_id = Column(String(30))

    journal = relationship("Journal", back_populates="identifiers")


class JournalScimago(Base):
    __tablename__ = "journal_scimago"

    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.id"), unique=True, nullable=False)
    sjr_score = Column(Float)
    sjr_best_quartile = Column(String(2))  # Q1-Q4
    h_index = Column(Integer)
    subject_category = Column(String(300))
    coverage_years = Column(String(50))
    snapshot_date = Column(DateTime)
    source_url = Column(String(500))
    fetch_method = Column(String(30))  # 'cloudscraper' | 'manual_csv'

    journal = relationship("Journal", back_populates="scimago")


class JournalScopus(Base):
    __tablename__ = "journal_scopus"

    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.id"), unique=True, nullable=False)
    citescore = Column(Float)
    percentile = Column(Float)
    asjc_codes = Column(String(200))
    active_status = Column(String(20))  # active | discontinued
    coverage_years = Column(String(50))
    snapshot_date = Column(DateTime)

    journal = relationship("Journal", back_populates="scopus")


class JournalMJL(Base):
    __tablename__ = "journal_mjl"

    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.id"), unique=True, nullable=False)
    jif = Column(Float)
    jif_quartile = Column(String(2))
    edition = Column(String(20))  # SCIE | SSCI | AHCI | ESCI
    is_partial = Column(Boolean, default=False)  # true = public title/ISSN only, no login
    snapshot_date = Column(DateTime)

    journal = relationship("Journal", back_populates="mjl")


class JournalDOAJ(Base):
    __tablename__ = "journal_doaj"

    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.id"), unique=True, nullable=False)
    in_doaj = Column(Boolean, default=False)
    has_apc = Column(Boolean)
    apc_amount = Column(Float)
    apc_currency = Column(String(10))
    waiver_policy_text = Column(Text)
    waiver_policy_url = Column(String(500))
    license_type = Column(String(50))
    review_process = Column(String(200))
    csv_snapshot_date = Column(DateTime)
    live_checked_at = Column(DateTime)
    diverged_from_csv = Column(Boolean, default=False)

    journal = relationship("Journal", back_populates="doaj")


class JournalAnnaUnivCFR(Base):
    __tablename__ = "journal_annauniv_cfr"

    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.id"), unique=True, nullable=False)
    listed = Column(Boolean, default=True)
    sl_no = Column(Integer)
    snapshot_date = Column(DateTime)

    journal = relationship("Journal", back_populates="annauniv_cfr")


class JournalPublisherAPC(Base):
    """One row per (journal, publisher, list_type) - a journal can appear
    under multiple publisher lists if data conflicts (rare) or during
    publisher transfer."""
    __tablename__ = "journal_publisher_apc"
    __table_args__ = (
        UniqueConstraint("journal_id", "publisher", "list_type", name="uq_journal_publisher_list"),
    )

    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.id"), nullable=False)
    publisher = Column(String(50), nullable=False)  # elsevier|wiley|springer|ieee|frontiers|mdpi|acm|oup|plos|tandf|sage
    list_type = Column(String(20))  # fully-oa | hybrid
    apc_amount = Column(Float)
    currency = Column(String(10))
    source_url = Column(String(500))
    snapshot_date = Column(DateTime)

    journal = relationship("Journal", back_populates="publisher_apcs")


class CountryIncomeClassification(Base):
    """World Bank income tier per country - authoritative source for the
    country-level rule most publisher APC waivers are actually keyed to."""
    __tablename__ = "country_income_classification"

    id = Column(Integer, primary_key=True)
    country_code = Column(String(3), unique=True, nullable=False)  # ISO3
    country_name = Column(String(150))
    income_group = Column(String(20))  # low | lower_middle | upper_middle | high
    source = Column(String(100), default="World Bank API")
    updated_at = Column(DateTime, default=_now)


class PublisherWaiverPolicy(Base):
    """Hand-curated, cited policy per publisher - waivers are a country-tier
    rule, not per-journal data, so this is reviewed periodically rather than
    scraped per-journal."""
    __tablename__ = "publisher_waiver_policy"

    id = Column(Integer, primary_key=True)
    publisher = Column(String(50), unique=True, nullable=False)
    policy_type = Column(String(40))  # automatic_by_country | research4life_tier | case_by_case
    full_waiver_income_groups = Column(String(100))  # e.g. "low"
    discount_pct = Column(Float)
    discount_income_groups = Column(String(100))  # e.g. "lower_middle"
    policy_url = Column(String(500), nullable=False)
    notes = Column(Text)
    last_reviewed_at = Column(DateTime, default=_now)


class JournalAPCConsolidated(Base):
    __tablename__ = "journal_apc_consolidated"

    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.id"), unique=True, nullable=False)
    apc_usd = Column(Float)
    apc_source = Column(String(50))  # doaj_live | publisher_bulk:<name> | openalex_estimate | unknown
    waiver_available = Column(Boolean)
    waiver_notes = Column(Text)
    confidence = Column(String(20))  # verified | estimated | unknown
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    journal = relationship("Journal", back_populates="apc_consolidated")


class JournalRiskFlag(Base):
    __tablename__ = "journal_risk_flags"

    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.id"), nullable=False)
    flag_type = Column(String(50))  # predatory_publisher | oa_not_in_doaj | suspicious_apc | volume_impact_mismatch
    reason = Column(Text)
    severity = Column(String(10))  # high | medium | low
    source = Column(String(100))

    journal = relationship("Journal", back_populates="risk_flags")


class ETLRunLog(Base):
    __tablename__ = "etl_run_log"

    id = Column(Integer, primary_key=True)
    source_name = Column(String(50), nullable=False)
    started_at = Column(DateTime, default=_now)
    finished_at = Column(DateTime)
    records_fetched = Column(Integer, default=0)
    records_upserted = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    status = Column(String(20))  # running | success | failed | partial
    error_summary = Column(Text)
