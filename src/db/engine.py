"""SQLite engine + session factory for the journal database.

File-based, zero-config, matches this repo's existing "no extra infra"
convention (same spirit as data/memory/*.json, just relational now).
Portable to Postgres later: only DATABASE_URL needs to change, the models
and every ingest script are engine-agnostic SQLAlchemy.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
_DB_PATH = os.path.join(_DATA_DIR, "journal_database.db")
DATABASE_URL = os.environ.get("JOURNAL_DB_URL", f"sqlite:///{_DB_PATH}")

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        os.makedirs(_DATA_DIR, exist_ok=True)
        connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
        _engine = create_engine(DATABASE_URL, connect_args=connect_args)
    return _engine


def init_db() -> None:
    """Create all tables if they don't exist. Idempotent."""
    Base.metadata.create_all(get_engine())


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope():
    """One transaction, committed on success, rolled back on error."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
