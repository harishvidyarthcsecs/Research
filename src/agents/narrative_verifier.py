"""
Narrative Verifier.

Mechanical enforcement of "unsupported sentence = build error": every sentence
the literature builder generates from the evidence table must carry a \\cite{key}
that resolves to a real EvidenceRow. If it doesn't, the sentence is unsupported
and the caller should treat that as a build failure, not silently drop it.

Pure functions, same style as latex_citation_reorder.py (reuses its \\cite{} regex
so both modules agree on what counts as a citation).
"""
import re
from typing import Dict, List

from ..models.data_models import EvidenceRow, NarrativeSentence

_CITE_RE = re.compile(r"\\cite[a-z]*\*?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
_ABBREVIATION_RE = re.compile(r"\b(?:et al|Fig|e\.g|i\.e|vs)\.", re.IGNORECASE)
_PERIOD_SENTINEL = "\ue000"


class UnsupportedSentenceError(Exception):
    """A generated sentence cites no key, or a key with no matching evidence row."""


def split_sentences(paragraph: str) -> List[str]:
    """Split on sentence-ending punctuation, keeping \\cite{} keys intact."""
    protected = _ABBREVIATION_RE.sub(
        lambda match: match.group(0).replace(".", _PERIOD_SENTINEL), paragraph.strip()
    )
    protected = re.sub(r"(?m)^[ \t]*(?:[-*•]|\d+[.)])[ \t]+", "", protected)
    protected = re.sub(r"[ \t]+•[ \t]*", "\n", protected)
    raw = re.split(r"(?:\r?\n)+|(?<=[.!?])[ \t]+", protected)
    return [s.replace(_PERIOD_SENTINEL, ".").strip() for s in raw if s.strip()]


def extract_cite_keys(sentence: str) -> List[str]:
    keys: List[str] = []
    for m in _CITE_RE.finditer(sentence):
        for key in m.group(1).split(","):
            key = key.strip()
            if key:
                keys.append(key)
    return keys


def verify_sentence(sentence: str, rows_by_key: Dict[str, EvidenceRow]) -> NarrativeSentence:
    keys = extract_cite_keys(sentence)
    if not keys:
        raise UnsupportedSentenceError(f"No \\cite{{}} key found: {sentence!r}")
    missing = [k for k in keys if k not in rows_by_key]
    if missing:
        raise UnsupportedSentenceError(f"Unknown citation key(s) {missing}: {sentence!r}")
    return NarrativeSentence(
        text=sentence,
        cite_keys=keys,
        source_row_ids=[rows_by_key[k].id for k in keys],
        verified=True,
    )


def verify_paragraph(paragraph: str, rows_by_key: Dict[str, EvidenceRow]) -> List[NarrativeSentence]:
    """Verify every sentence in a paragraph. Raises on the first unsupported one."""
    return [verify_sentence(s, rows_by_key) for s in split_sentences(paragraph)]


def verify_sentence_scored(sentence: str, rows_by_key: Dict[str, EvidenceRow]) -> NarrativeSentence:
    """Non-raising counterpart of verify_sentence.

    A sentence is verified only if it carries at least one \\cite{} key and every
    key resolves to an evidence row. Otherwise it is returned with verified=False
    instead of raising — this is the "scored grounding" behaviour the evaluation
    contrasts against the build-time reject in verify_sentence/verify_paragraph.
    """
    keys = extract_cite_keys(sentence)
    resolved = [k for k in keys if k in rows_by_key]
    verified = bool(keys) and len(resolved) == len(keys)
    return NarrativeSentence(
        text=sentence,
        cite_keys=keys,
        source_row_ids=[rows_by_key[k].id for k in resolved],
        verified=verified,
    )


def verify_paragraph_scored(paragraph: str, rows_by_key: Dict[str, EvidenceRow]) -> List[NarrativeSentence]:
    """Verify every sentence, never raising. Unsupported sentences come back with
    verified=False and are kept, not dropped."""
    return [verify_sentence_scored(s, rows_by_key) for s in split_sentences(paragraph)]
