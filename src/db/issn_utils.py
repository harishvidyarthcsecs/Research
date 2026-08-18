"""Shared ISSN normalization, used across the DB layer and all ETL ingest scripts.

Same convention `journal_metadata.py` already uses: OpenAlex/CrossRef/Scimago
all emit ISSNs inconsistently hyphenated/cased. Normalize to the canonical
NNNN-NNNX form so every source table joins on the same key.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Union

_ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dXx]$")


def normalize_issn(issn: Optional[str]) -> str:
    """Return a canonical NNNN-NNNX ISSN, or '' if not parseable."""
    if not issn:
        return ""
    cleaned = issn.strip().upper().replace(" ", "")
    if len(cleaned) == 8 and "-" not in cleaned:
        cleaned = f"{cleaned[:4]}-{cleaned[4:]}"
    return cleaned if _ISSN_RE.match(cleaned) else ""


def all_issns(*candidates: Union[Optional[str], Iterable[Optional[str]]]) -> list:
    """Normalize and dedupe any mix of single ISSNs and ISSN lists, preserving order."""
    seen = set()
    out = []
    for candidate in candidates:
        values = candidate if isinstance(candidate, (list, tuple, set)) else [candidate]
        for raw in values:
            norm = normalize_issn(raw)
            if norm and norm not in seen:
                seen.add(norm)
                out.append(norm)
    return out
