"""Citation network explorer using OpenAlex (primary) + Semantic Scholar (fallback)."""
from __future__ import annotations
import os
import re
import time
import requests


OA_BASE = "https://api.openalex.org"
SS_BASE = "https://api.semanticscholar.org/graph/v1"
OA_HEADERS = {"User-Agent": "ResearchAgent/1.0 (mailto:research@example.com)"}
SS_HEADERS = {"User-Agent": "ResearchAgent/1.0"}


class CitationNetworkAgent:
    def __init__(self):
        ss_key = os.getenv('SEMANTIC_SCHOLAR_API_KEY', '')
        self.ss_headers = dict(SS_HEADERS)
        if ss_key:
            self.ss_headers["x-api-key"] = ss_key

    # ── OpenAlex ────────────────────────────────────────────────────────────

    def _oa_search_paper(self, query: str) -> dict | None:
        """Find a paper on OpenAlex by title or DOI."""
        # DOI lookup
        if query.startswith("10.") or "doi.org" in query:
            doi = query.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
            return self._oa_get_by_doi(doi)

        try:
            resp = requests.get(
                f"{OA_BASE}/works",
                params={
                    "search": query,
                    "select": "id,title,abstract_inverted_index,authorships,publication_year,primary_location,cited_by_count,referenced_works,doi",
                    "per-page": 1,
                    "sort": "relevance_score:desc",
                },
                headers=OA_HEADERS,
                timeout=15,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    return results[0]
        except Exception as e:
            print(f"OpenAlex paper search error: {e}")
        return None

    def _oa_get_by_doi(self, doi: str) -> dict | None:
        try:
            resp = requests.get(
                f"{OA_BASE}/works/doi:{doi}",
                headers=OA_HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"OpenAlex DOI lookup error: {e}")
        return None

    def _oa_get_references(self, work_id: str, limit: int = 25) -> list:
        """Get referenced works for an OpenAlex work ID."""
        try:
            resp = requests.get(
                f"{OA_BASE}/works",
                params={
                    "filter": f"cites:{work_id}",
                    "select": "id,title,authorships,publication_year,primary_location,cited_by_count,doi",
                    "per-page": min(limit, 25),
                    "sort": "cited_by_count:desc",
                },
                headers=OA_HEADERS,
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
        except Exception as e:
            print(f"OpenAlex citing papers error: {e}")
        return []

    def _oa_get_reference_details(self, ref_ids: list, limit: int = 25) -> list:
        """Fetch details for a list of OpenAlex work IDs (references)."""
        if not ref_ids:
            return []
        try:
            ids_str = "|".join(ref_ids[:limit])
            resp = requests.get(
                f"{OA_BASE}/works",
                params={
                    "filter": f"openalex_id:{ids_str}",
                    "select": "id,title,authorships,publication_year,primary_location,cited_by_count,doi",
                    "per-page": limit,
                },
                headers=OA_HEADERS,
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
        except Exception as e:
            print(f"OpenAlex reference details error: {e}")
        return []

    def _oa_to_node(self, work: dict, node_type: str) -> dict:
        """Convert OpenAlex work dict to network node."""
        authors = work.get("authorships") or []
        first_author = ""
        if authors:
            auth = authors[0].get("author") or {}
            first_author = auth.get("display_name", "")

        loc = work.get("primary_location") or {}
        source = loc.get("source") or {}
        venue = source.get("display_name", "")

        doi_raw = work.get("doi") or ""
        doi = doi_raw.replace("https://doi.org/", "").replace("http://doi.org/", "")

        oa_id = work.get("id", "")
        node_id = doi if doi else oa_id

        return {
            "id": node_id or work.get("title", "unknown"),
            "title": (work.get("title") or "Unknown")[:80],
            "year": work.get("publication_year"),
            "venue": venue,
            "citation_count": work.get("cited_by_count", 0),
            "first_author": first_author,
            "type": node_type,
            "doi": doi,
            "oa_id": oa_id,
        }

    # ── Semantic Scholar fallback ───────────────────────────────────────────

    def _ss_search_paper(self, query: str) -> dict | None:
        for attempt in range(2):
            try:
                resp = requests.get(
                    f"{SS_BASE}/paper/search",
                    params={
                        "query": query,
                        "fields": "paperId,title,abstract,authors,year,venue,citationCount,referenceCount,externalIds",
                        "limit": 1,
                    },
                    headers=self.ss_headers,
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    return data[0] if data else None
                if resp.status_code == 429:
                    time.sleep(8)
            except Exception as e:
                print(f"SS search error: {e}")
                if attempt < 1:
                    time.sleep(4)
        return None

    def _ss_get_citations(self, paper_id: str, limit: int = 20) -> list:
        try:
            resp = requests.get(
                f"{SS_BASE}/paper/{paper_id}/citations",
                params={"fields": "paperId,title,authors,year,venue,citationCount", "limit": limit},
                headers=self.ss_headers,
                timeout=15,
            )
            if resp.status_code == 200:
                return [item.get("citingPaper", {}) for item in resp.json().get("data", [])]
        except Exception as e:
            print(f"SS citations error: {e}")
        return []

    def _ss_get_references(self, paper_id: str, limit: int = 20) -> list:
        try:
            resp = requests.get(
                f"{SS_BASE}/paper/{paper_id}/references",
                params={"fields": "paperId,title,authors,year,venue,citationCount", "limit": limit},
                headers=self.ss_headers,
                timeout=15,
            )
            if resp.status_code == 200:
                return [item.get("citedPaper", {}) for item in resp.json().get("data", [])]
        except Exception as e:
            print(f"SS references error: {e}")
        return []

    # ── Public API ──────────────────────────────────────────────────────────

    def get_network(self, query: str, depth: int = 1) -> dict:
        """Build citation network, using OpenAlex first, Semantic Scholar as fallback."""

        # ── Try OpenAlex first ──
        root_oa = self._oa_search_paper(query.strip())
        if root_oa:
            oa_id = root_oa.get("id", "")
            abstract = _reconstruct_abstract(root_oa.get("abstract_inverted_index") or {})
            authors = [(a.get("author") or {}).get("display_name", "") for a in (root_oa.get("authorships") or [])[:5]]
            loc = root_oa.get("primary_location") or {}
            source = loc.get("source") or {}
            doi_raw = root_oa.get("doi") or ""
            doi = doi_raw.replace("https://doi.org/", "")
            root_node = self._oa_to_node(root_oa, "root")

            # Citing papers (papers that cite this one)
            citing_works = self._oa_get_references(oa_id, limit=20)
            # Referenced works (papers this one cites)
            ref_ids = root_oa.get("referenced_works") or []
            ref_works = self._oa_get_reference_details(ref_ids, limit=20)

            nodes = {root_node["id"]: root_node}
            links = []

            for w in citing_works:
                n = self._oa_to_node(w, "citing")
                if n["id"] not in nodes:
                    nodes[n["id"]] = n
                links.append({"source": n["id"], "target": root_node["id"], "type": "cites"})

            for w in ref_works:
                n = self._oa_to_node(w, "reference")
                if n["id"] not in nodes:
                    nodes[n["id"]] = n
                links.append({"source": root_node["id"], "target": n["id"], "type": "cites"})

            return {
                "root_paper": {
                    "id": oa_id,
                    "title": root_oa.get("title", ""),
                    "abstract": abstract[:400],
                    "year": root_oa.get("publication_year"),
                    "venue": source.get("display_name", ""),
                    "citation_count": root_oa.get("cited_by_count", 0),
                    "reference_count": len(ref_ids),
                    "authors": authors,
                    "doi": doi,
                    "source": "OpenAlex",
                },
                "nodes": list(nodes.values()),
                "links": links,
                "stats": {
                    "total_nodes": len(nodes),
                    "citing_papers": len(citing_works),
                    "reference_papers": len(ref_works),
                },
            }

        # ── Fallback: Semantic Scholar ──
        root_ss = self._ss_search_paper(query.strip())
        if not root_ss:
            return {"error": f"Could not find a paper matching: '{query}'. Try a different title or DOI.", "nodes": [], "links": []}

        paper_id = root_ss.get("paperId", "")
        citing = self._ss_get_citations(paper_id, limit=20)
        refs = self._ss_get_references(paper_id, limit=20)

        def ss_node(p, ntype):
            authors_raw = p.get("authors") or []
            first = authors_raw[0].get("name", "") if authors_raw else ""
            pid = p.get("paperId") or p.get("title", "unknown")
            return {
                "id": pid,
                "title": (p.get("title") or "Unknown")[:80],
                "year": p.get("year"),
                "venue": p.get("venue", ""),
                "citation_count": p.get("citationCount", 0),
                "first_author": first,
                "type": ntype,
            }

        nodes = {}
        links = []
        root_n = ss_node(root_ss, "root")
        nodes[root_n["id"]] = root_n

        for c in citing:
            if c and c.get("paperId"):
                n = ss_node(c, "citing")
                nodes[n["id"]] = n
                links.append({"source": n["id"], "target": root_n["id"], "type": "cites"})

        for r in refs:
            if r and r.get("paperId"):
                n = ss_node(r, "reference")
                nodes[n["id"]] = n
                links.append({"source": root_n["id"], "target": n["id"], "type": "cites"})

        authors = [a.get("name", "") for a in (root_ss.get("authors") or [])[:5]]
        return {
            "root_paper": {
                "id": paper_id,
                "title": root_ss.get("title", ""),
                "abstract": (root_ss.get("abstract") or "")[:400],
                "year": root_ss.get("year"),
                "venue": root_ss.get("venue", ""),
                "citation_count": root_ss.get("citationCount", 0),
                "reference_count": root_ss.get("referenceCount", 0),
                "authors": authors,
                "source": "Semantic Scholar",
            },
            "nodes": list(nodes.values()),
            "links": links,
            "stats": {
                "total_nodes": len(nodes),
                "citing_papers": len(citing),
                "reference_papers": len(refs),
            },
        }


def _reconstruct_abstract(inverted_index: dict) -> str:
    if not inverted_index:
        return ""
    try:
        positions = []
        for word, pos_list in inverted_index.items():
            for pos in pos_list:
                positions.append((pos, word))
        positions.sort()
        return " ".join(w for _, w in positions)
    except Exception:
        return ""
