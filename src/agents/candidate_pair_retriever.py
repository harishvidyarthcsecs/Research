"""
Candidate pair retrieval for contradiction detection.

Selects the top-K most similar cross-paper claim pairs so the LLM judge only
scores a bounded number of pairs instead of all O(n^2) combinations.
Uses TF-IDF cosine similarity when scikit-learn is available, with a pure
Python Jaccard fallback otherwise.
"""
from __future__ import annotations

import re
from itertools import combinations
from typing import List, Tuple

from ..models.data_models import Claim

# Similarity boost for pairs sharing experimental context: contradictions are
# far more likely between claims about the same dataset or metric.
_DATASET_BOOST = 0.15
_METRIC_BOOST = 0.10

_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "are", "was", "were", "we", "our", "this",
    "that", "it", "as", "be", "can", "which", "from",
}


def _context_boost(c1: Claim, c2: Claim) -> float:
    boost = 0.0
    if set(c1.datasets) & set(c2.datasets):
        boost += _DATASET_BOOST
    if set(c1.metrics.keys()) & set(c2.metrics.keys()):
        boost += _METRIC_BOOST
    return boost


def _tfidf_similarities(statements: List[str]):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
    matrix = vectorizer.fit_transform(statements)
    return cosine_similarity(matrix)


def _jaccard(a: str, b: str) -> float:
    words_a = set(re.findall(r"\b\w+\b", a.lower())) - _STOP_WORDS
    words_b = set(re.findall(r"\b\w+\b", b.lower())) - _STOP_WORDS
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def retrieve_candidate_pairs(
    claims: List[Claim],
    top_k: int = 40,
    min_similarity: float = 0.15,
) -> List[Tuple[Claim, Claim, float]]:
    """Return the top_k most similar cross-paper claim pairs.

    Each result is (claim_a, claim_b, score) sorted by descending score,
    where score = text similarity + dataset/metric context boosts.
    """
    if len(claims) < 2:
        return []

    sim_matrix = None
    try:
        sim_matrix = _tfidf_similarities([c.statement for c in claims])
    except Exception:
        pass  # sklearn unavailable or vectorizer failed; use Jaccard below

    scored: List[Tuple[Claim, Claim, float]] = []
    for i, j in combinations(range(len(claims)), 2):
        c1, c2 = claims[i], claims[j]
        if c1.paper_id == c2.paper_id:
            continue
        if sim_matrix is not None:
            similarity = float(sim_matrix[i, j])
        else:
            similarity = _jaccard(c1.statement, c2.statement)
        if similarity < min_similarity:
            continue
        scored.append((c1, c2, similarity + _context_boost(c1, c2)))

    scored.sort(key=lambda item: item[2], reverse=True)
    return scored[:top_k]
