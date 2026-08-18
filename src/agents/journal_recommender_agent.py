"""Journal fit recommender using OpenAlex + DOAJ + Scimago, with LLM fit ranking.

Quartiles come from `journal_metadata`, which resolves them against real data
and labels their provenance. The LLM is used only to judge *fit* between an
abstract and a journal's scope — never to recall a quartile, which it cannot do
reliably.
"""
from __future__ import annotations
import re
import json
import time
import requests
from collections import Counter
from src.agents.llm_client import chat as llm_chat, get_provider
from src.agents.journal_metadata import data_status, resolve_journal


# Broad field keywords → canonical field name for OpenAlex search
_FIELD_MAP = [
    (["graph", "vertex", "edge", "biswapped", "wiener", "topological index",
      "chromatic", "clique", "spanning tree", "hamiltonian"],
     ["Discrete Mathematics", "Graph Theory", "Combinatorics"]),
    (["neural network", "deep learning", "machine learning", "transformer",
      "attention", "convolutional", "classification", "training"],
     ["Machine Learning", "Artificial Intelligence", "Deep Learning"]),
    (["dna", "rna", "protein", "gene", "genome", "sequencing", "cell", "enzyme"],
     ["Bioinformatics", "Molecular Biology", "Genomics"]),
    (["quantum", "photon", "laser", "optical", "waveguide", "semiconductor"],
     ["Photonics", "Quantum Physics", "Applied Physics"]),
    (["climate", "carbon", "emission", "temperature", "atmosphere", "greenhouse"],
     ["Climate Science", "Environmental Science"]),
    (["cancer", "tumor", "clinical", "patient", "treatment", "drug", "therapy"],
     ["Oncology", "Medicine", "Clinical Research"]),
    (["supply chain", "inventory", "logistics", "scheduling", "optimization"],
     ["Operations Research", "Management Science"]),
    (["blockchain", "cryptography", "privacy", "security", "encryption"],
     ["Cybersecurity", "Cryptography", "Computer Networks"]),
    (["nanoparticle", "nanomaterial", "synthesis", "polymer", "composite"],
     ["Materials Science", "Nanotechnology"]),
    (["econom", "market", "gdp", "inflation", "monetary", "fiscal"],
     ["Economics", "Finance"]),
]


def _detect_broad_field(abstract: str) -> list[str]:
    """Map abstract keywords to broad searchable field names."""
    text = abstract.lower()
    for kws, fields in _FIELD_MAP:
        if any(kw in text for kw in kws):
            return fields
    return []


_PURE_FIELDS = {"mathematics", "physics", "chemistry", "biology",
                "environmental science", "economics", "psychology",
                "medicine", "materials science", "statistics"}

_MATH_NAME_HINTS = {"mathematic", "combinatori", "graph", "algebra",
                    "topology", "geometry", "number theory", "discrete",
                    "analytic", "probability", "statistic", "logic"}


def _journal_field(journal: dict) -> str:
    """
    Determine the primary field for a journal from OpenAlex topics.
    Journals that straddle Math/CS are assigned to 'mathematics' so that
    Scimago-style quartile thresholds are applied correctly (Scimago uses
    lower IF thresholds for pure math journals than for CS).
    """
    topics = journal.get("topics") or []
    field_counts: dict[str, int] = {}
    for t in topics:
        fname = (t.get("field") or {}).get("display_name", "")
        if fname:
            field_counts[fname.lower()] = field_counts.get(fname.lower(), 0) + 1
    if not field_counts:
        return ""

    # If the journal name itself contains math-related words and "mathematics"
    # appears in any topic, promote it regardless of count
    name = (journal.get("display_name") or "").lower()
    if "mathematics" in field_counts and any(h in name for h in _MATH_NAME_HINTS):
        return "mathematics"

    # Pure-science fields get a +0.5 bonus so they beat CS/Engineering at equal count
    best = max(field_counts, key=lambda f: field_counts[f] + (0.5 if f in _PURE_FIELDS else 0))
    return best


_SAFE_URL_RE = re.compile(r'^https?://.{4,}', re.I)
_BAD_EXT_RE  = re.compile(r'\.(pdf|xls|xlsx|doc|docx|zip|rar|gz|exe|dmg)(\?.*)?$', re.I)

def _safe_homepage(url: str) -> str:
    """Return url only if it is a safe http/https web page, not a file download."""
    url = (url or "").strip()
    if not _SAFE_URL_RE.match(url):
        return ""
    if _BAD_EXT_RE.search(url):
        return ""
    if len(url) > 512:
        return ""
    return url


def _scimago_url(issn: str, name: str) -> str:
    if issn:
        return f"https://www.scimagojr.com/journalsearch.php?q={issn}&type=j"
    safe = re.sub(r'[^a-zA-Z0-9 ]', '', name)
    return f"https://www.scimagojr.com/journalsearch.php?q={'+'.join(safe.split()[:4])}&type=j"


class JournalRecommenderAgent:
    def __init__(self):
        self._has_llm = get_provider() is not None
        self.openalex_base = "https://api.openalex.org"
        self.headers = {"User-Agent": "ResearchAgent/1.0 (mailto:research@example.com)"}

    def _get_concepts_from_abstract(self, abstract: str, field: str) -> list:
        stops = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
                 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                 'could', 'should', 'may', 'might', 'must', 'shall', 'that', 'this',
                 'these', 'those', 'we', 'our', 'us', 'it', 'its', 'as', 'such',
                 'which', 'who', 'whom', 'what', 'when', 'where', 'how', 'than',
                 'both', 'each', 'more', 'most', 'other', 'into', 'through', 'also',
                 'can', 'paper', 'study', 'results', 'using', 'based', 'show', 'shows',
                 'proposed', 'present', 'method', 'approach', 'model', 'data', 'novel',
                 'new', 'first', 'second', 'two', 'three', 'however', 'thus', 'therefore',
                 'while', 'within', 'between', 'among', 'across', 'their', 'they'}
        words = re.findall(r'\b[a-zA-Z]{3,}\b', abstract)
        bigrams = []
        for i in range(len(words) - 1):
            w1, w2 = words[i].lower(), words[i+1].lower()
            if w1 not in stops and w2 not in stops and len(w1) > 3 and len(w2) > 3:
                bigrams.append(f"{w1} {w2}")
        single = [w.lower() for w in words if w.lower() not in stops and len(w) > 4]
        freq = Counter(bigrams + single)
        concepts = [w for w, _ in freq.most_common(12) if len(w) > 5][:8]
        if field and field.lower() not in [c.lower() for c in concepts]:
            concepts.insert(0, field)
        return concepts[:8]

    def _rank_with_llm(self, abstract: str, journals: list) -> list | None:
        if not self._has_llm:
            return None
        journal_list = []
        for i, j in enumerate(journals[:12]):
            ss = j.get("summary_stats") or {}
            h_idx = ss.get('h_index', 'N/A')
            impact = round(ss.get('2yr_mean_citedness', 0) or 0, 2)
            topics_raw = j.get("topics") or []
            topics = [t.get("display_name", "") for t in topics_raw[:3]]
            journal_list.append(f"[{i+1}] {j.get('display_name', 'Unknown')} | H-index: {h_idx} | Impact: {impact} | Topics: {', '.join(topics)}")

        prompt = f"""You are an academic publishing expert. Given this research abstract, rank these journals by fit.

ABSTRACT:
{abstract[:1000]}

JOURNALS:
{chr(10).join(journal_list)}

For each journal rate fit_score (0-100) and write fit_reason (1-2 sentences) and submission_tips (1 tip).

Return ONLY a JSON array:
[{{"journal_index":1,"fit_score":85,"fit_reason":"...","submission_tips":"...","open_access":false}}]"""

        try:
            raw = llm_chat(prompt, max_tokens=2000).strip()
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            print(f"LLM ranking error: {e}")
        return None

    def _simple_score(self, abstract: str, journal: dict, concepts: list) -> int:
        text = (abstract + " " + " ".join(concepts)).lower()
        topics_raw = journal.get("topics") or []
        topic_names = " ".join(t.get("display_name", "") for t in topics_raw[:10]).lower()
        journal_name = (journal.get("display_name") or "").lower()
        score = 0
        for concept in concepts:
            if concept.lower() in topic_names:
                score += 15
            if concept.lower() in journal_name:
                score += 10
        ss = journal.get("summary_stats") or {}
        h = ss.get('h_index', 0) or 0
        if h > 200:
            score += 5
        elif h > 100:
            score += 3
        return min(score, 95)

    def _search_journals_openalex(self, queries: list[str]) -> list:
        seen_ids: set = set()
        all_journals: list = []
        for query in queries[:4]:
            try:
                resp = requests.get(
                    f"{self.openalex_base}/sources",
                    params={
                        "search": query,
                        "filter": "type:journal",
                        "per-page": 10,
                        "sort": "cited_by_count:desc",
                    },
                    headers=self.headers,
                    timeout=15,
                )
                if resp.status_code == 200:
                    for j in resp.json().get("results", []):
                        jid = j.get("id", "")
                        if jid and jid not in seen_ids:
                            seen_ids.add(jid)
                            all_journals.append(j)
                time.sleep(0.25)
            except Exception as e:
                print(f"OpenAlex search error for '{query}': {e}")
        return all_journals

    def recommend(self, abstract: str, field: str = "") -> dict:
        concepts = self._get_concepts_from_abstract(abstract, field)

        # Build search queries: explicit field first, then broad field detection, then concepts
        queries: list[str] = []
        if field:
            queries.append(field)
        broad = _detect_broad_field(abstract)
        queries.extend(broad[:2])
        if concepts:
            queries.append(" ".join(concepts[:3]))

        # Deduplicate and always have at least one query
        seen: set = set()
        deduped: list[str] = []
        for q in queries:
            if q.lower() not in seen:
                seen.add(q.lower())
                deduped.append(q)
        if not deduped:
            deduped = ["multidisciplinary research"]

        journals_raw = self._search_journals_openalex(deduped)

        if not journals_raw:
            return {
                "concepts_extracted": concepts,
                "journals_found": 0,
                "recommendations": [],
                "top_pick": None,
                "error": "No journals found. OpenAlex may be unavailable.",
            }

        # The LLM ranks fit only. Quartiles come from measured data below.
        rankings = self._rank_with_llm(abstract, journals_raw)

        results = []

        def _build_entry(j: dict, fit_score: int, fit_reason: str, submission_tips: str) -> dict:
            facts = resolve_journal(j)
            issn = facts["issn"] or j.get("issn_l", "")

            return {
                "name": facts["name"] or "Unknown",
                "issn": issn,
                "publisher": facts["publisher"],
                "homepage": _safe_homepage(j.get("homepage_url", "")),
                "scimago_url": _scimago_url(issn, facts["name"]),
                "h_index": facts["h_index"],
                "impact_factor": facts["citedness"],
                "works_count": facts["works"],
                "field": facts["field"],
                "is_oa": facts["is_oa"],
                "in_doaj": facts["in_doaj"],
                "apc_usd": facts["apc_usd"],
                "quartile": facts["quartile"],
                "quartile_source": facts["quartile_source"],
                "quartile_source_label": facts["quartile_source_label"],
                "quartile_field": facts["quartile_field"],
                "risk_flags": facts["risk_flags"],
                "in_reference_index": facts["in_reference_index"],
                "fit_score": fit_score,
                "fit_reason": fit_reason,
                "submission_tips": submission_tips,
            }

        if rankings:
            for r in rankings:
                idx = r.get("journal_index", 1) - 1
                if 0 <= idx < len(journals_raw):
                    j = journals_raw[idx]
                    results.append(_build_entry(
                        j, r.get("fit_score", 0),
                        r.get("fit_reason", ""), r.get("submission_tips", "")))
        else:
            for j in journals_raw:
                topics_raw = j.get("topics") or []
                topic_names = [t.get("display_name", "") for t in topics_raw[:3]]
                score = self._simple_score(abstract, j, concepts)
                results.append(_build_entry(
                    j, score,
                    f"Covers {', '.join(topic_names[:2]) or field or 'related topics'}.",
                    "Review the journal's author guidelines and scope before submitting."))

        results.sort(key=lambda x: x["fit_score"], reverse=True)

        return {
            "concepts_extracted": concepts,
            "broad_fields_detected": broad,
            "journals_found": len(journals_raw),
            "recommendations": results[:10],
            "top_pick": results[0] if results else None,
            "ai_ranked": rankings is not None,
            "data_status": data_status(),
        }
