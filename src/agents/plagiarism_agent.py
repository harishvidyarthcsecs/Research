"""
Plagiarism & similarity checker.
- Searches OpenAlex + CrossRef + Semantic Scholar with multiple queries
- Uses available LLM (Grok/Claude/Groq/Ollama) for sentence-level analysis
- Returns per-sentence match highlights, overall score, and source links
"""
from __future__ import annotations
import re
import time
import json
import requests


OA_BASE  = "https://api.openalex.org"
SS_BASE  = "https://api.semanticscholar.org/graph/v1"
CR_BASE  = "https://api.crossref.org/works"
OA_HDR   = {"User-Agent": "ResearchAgent/1.0 (mailto:research@example.com)"}
SS_HDR   = {"User-Agent": "ResearchAgent/1.0"}


# ── helpers ────────────────────────────────────────────────────────────────

def _reconstruct_abstract(inv: dict) -> str:
    if not inv:
        return ""
    try:
        pairs = [(pos, w) for w, ps in inv.items() for pos in ps]
        return " ".join(w for _, w in sorted(pairs))
    except Exception:
        return ""


def _split_sentences(text: str) -> list[str]:
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in raw if len(s.split()) >= 6]


def _build_queries(text: str) -> list[str]:
    """Generate 3 diverse search queries from the text."""
    sentences = _split_sentences(text)
    queries = []
    # Q1: first meaningful sentence
    if sentences:
        queries.append(" ".join(sentences[0].split()[:12]))
    # Q2: middle sentence
    if len(sentences) > 2:
        mid = sentences[len(sentences) // 2]
        queries.append(" ".join(mid.split()[:12]))
    # Q3: key noun phrases (simple extraction)
    words = re.findall(r'\b[A-Za-z][a-z]{3,}\b', text)
    stops = {'that','this','with','from','have','been','they','their','which',
             'were','also','more','some','when','than','then','into','used',
             'show','these','paper','study','using','based','model','method',
             'approach','proposed','results','data','novel','first','second'}
    kw = [w.lower() for w in words if w.lower() not in stops]
    from collections import Counter
    top_kw = [w for w, _ in Counter(kw).most_common(8)]
    if top_kw:
        queries.append(" ".join(top_kw[:6]))
    return list(dict.fromkeys(queries))  # deduplicate


# ── search backends ────────────────────────────────────────────────────────

def _search_openalex(query: str, limit: int = 8) -> list[dict]:
    try:
        resp = requests.get(
            f"{OA_BASE}/works",
            params={
                "search": query,
                "filter": "type:article",
                "select": "id,title,abstract_inverted_index,authorships,publication_year,primary_location,cited_by_count,doi",
                "per-page": limit,
                "sort": "relevance_score:desc",
            },
            headers=OA_HDR,
            timeout=15,
        )
        if resp.status_code == 200:
            out = []
            for r in resp.json().get("results", []):
                authors = [(a.get("author") or {}).get("display_name", "")
                           for a in (r.get("authorships") or [])[:3]]
                loc = (r.get("primary_location") or {})
                source = (loc.get("source") or {})
                doi = (r.get("doi") or "").replace("https://doi.org/", "")
                out.append({
                    "title": r.get("title", ""),
                    "abstract": _reconstruct_abstract(r.get("abstract_inverted_index") or {}),
                    "authors": authors,
                    "year": r.get("publication_year"),
                    "venue": source.get("display_name", ""),
                    "citation_count": r.get("cited_by_count", 0),
                    "doi": doi,
                    "url": f"https://doi.org/{doi}" if doi else "",
                    "source": "OpenAlex",
                })
            return out
    except Exception as e:
        print(f"OpenAlex search error: {e}")
    return []


def _search_crossref(query: str, limit: int = 5) -> list[dict]:
    try:
        resp = requests.get(
            CR_BASE,
            params={"query": query, "rows": limit, "select": "title,author,published,container-title,DOI,abstract,is-referenced-by-count"},
            headers={"User-Agent": "ResearchAgent/1.0 (mailto:research@example.com)"},
            timeout=12,
        )
        if resp.status_code == 200:
            out = []
            for item in resp.json().get("message", {}).get("items", []):
                title = (item.get("title") or [""])[0]
                authors = [f"{a.get('given','')} {a.get('family','')}".strip()
                           for a in (item.get("author") or [])[:3]]
                year = None
                pub = item.get("published") or item.get("published-print") or {}
                dp = pub.get("date-parts", [[]])
                if dp and dp[0]:
                    year = dp[0][0]
                doi = item.get("DOI", "")
                abstract = re.sub(r'<[^>]+>', '', item.get("abstract") or "")
                venue = (item.get("container-title") or [""])[0]
                out.append({
                    "title": title,
                    "abstract": abstract[:800],
                    "authors": authors,
                    "year": year,
                    "venue": venue,
                    "citation_count": item.get("is-referenced-by-count", 0),
                    "doi": doi,
                    "url": f"https://doi.org/{doi}" if doi else "",
                    "source": "CrossRef",
                })
            return out
    except Exception as e:
        print(f"CrossRef search error: {e}")
    return []


def _search_semantic_scholar(query: str, limit: int = 8) -> list[dict]:
    for attempt in range(2):
        try:
            resp = requests.get(
                f"{SS_BASE}/paper/search",
                params={
                    "query": query[:200],
                    "fields": "title,abstract,authors,year,venue,externalIds,citationCount",
                    "limit": limit,
                },
                headers=SS_HDR,
                timeout=15,
            )
            if resp.status_code == 200:
                out = []
                for p in resp.json().get("data", []):
                    doi = (p.get("externalIds") or {}).get("DOI", "")
                    out.append({
                        "title": p.get("title", ""),
                        "abstract": (p.get("abstract") or "")[:800],
                        "authors": [a.get("name", "") for a in (p.get("authors") or [])[:3]],
                        "year": p.get("year"),
                        "venue": p.get("venue", ""),
                        "citation_count": p.get("citationCount", 0),
                        "doi": doi,
                        "url": f"https://doi.org/{doi}" if doi else "",
                        "source": "Semantic Scholar",
                    })
                return out
            if resp.status_code == 429:
                time.sleep(6 * (attempt + 1))
        except Exception as e:
            print(f"Semantic Scholar error (attempt {attempt+1}): {e}")
            time.sleep(3)
    return []


# ── LLM analysis ───────────────────────────────────────────────────────────

def _llm_analyze(input_text: str, papers: list[dict]) -> dict | None:
    """Use the available LLM for deep sentence-level similarity analysis."""
    try:
        from src.agents.llm_client import chat, get_provider
        if not get_provider():
            return None
    except Exception:
        return None

    paper_list = []
    for i, p in enumerate(papers[:12]):
        title    = (p.get("title") or "")[:120]
        abstract = (p.get("abstract") or "")[:400]
        paper_list.append(f"[{i+1}] TITLE: {title}\nABSTRACT: {abstract}")

    sentences = _split_sentences(input_text)
    sentences_block = "\n".join(f"S{i+1}: {s}" for i, s in enumerate(sentences[:15]))

    prompt = f"""You are a plagiarism detection expert. Analyze the submitted text sentence by sentence and compare against {len(papers)} academic papers.

SUBMITTED TEXT SENTENCES:
{sentences_block}

COMPARISON PAPERS:
{chr(10).join(paper_list)}

For EACH paper that has meaningful overlap (>20% similarity), return an analysis.
For EACH matching sentence, state which paper it resembles and why.

Return ONLY a valid JSON object:
{{
  "overall_score": 45,
  "overall_risk": "MEDIUM",
  "summary": "2 sentences closely match Paper 3, overall moderate similarity",
  "papers": [
    {{
      "paper_index": 3,
      "similarity_score": 67,
      "risk_level": "HIGH",
      "matching_sentences": ["S1", "S3"],
      "overlapping_ideas": ["transformer architecture", "attention mechanism"],
      "assessment": "The first sentence directly mirrors the abstract of paper 3..."
    }}
  ],
  "sentence_risks": {{
    "S1": "HIGH",
    "S2": "LOW",
    "S3": "MEDIUM"
  }}
}}

risk_level rules: HIGH ≥60%, MEDIUM 30–59%, LOW <30%
If no meaningful overlap, return overall_score: 5 and empty papers array."""

    try:
        raw = chat(prompt, max_tokens=3000).strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"LLM analysis error: {e}")
    return None


# ── simple keyword fallback ────────────────────────────────────────────────

def _keyword_score(text: str, paper: dict) -> int:
    stops = {'this','that','with','from','have','been','they','their','which',
             'were','also','more','some','when','than','then','into','paper',
             'study','using','based','model','method','results','these','those'}
    tw = set(re.findall(r'\b[a-z]{4,}\b', text.lower())) - stops
    pw = set(re.findall(r'\b[a-z]{4,}\b',
             ((paper.get("title") or "") + " " + (paper.get("abstract") or "")).lower())) - stops
    if not tw or not pw:
        return 0
    overlap = len(tw & pw)
    return min(int(overlap / min(len(tw), len(pw)) * 180), 90)


# ── public API ─────────────────────────────────────────────────────────────

class PlagiarismCheckerAgent:

    def check(self, text: str) -> dict:
        queries = _build_queries(text)
        print(f"[Plagiarism] Queries: {queries}")

        # Collect papers from all sources, deduplicate by title
        seen_titles: set[str] = set()
        all_papers: list[dict] = []

        for q in queries:
            for fn in [_search_openalex, _search_crossref, _search_semantic_scholar]:
                for p in fn(q, limit=6):
                    t = (p.get("title") or "").lower()[:60]
                    if t and t not in seen_titles:
                        seen_titles.add(t)
                        all_papers.append(p)
                time.sleep(0.15)

        print(f"[Plagiarism] Total papers found: {len(all_papers)}")

        if not all_papers:
            return {
                "overall_risk": "UNKNOWN",
                "overall_score": 0,
                "matches": [],
                "papers_checked": 0,
                "input_length": len(text.split()),
                "summary": "Could not reach literature databases. Check your internet connection.",
                "ai_analyzed": False,
                "sentences": [],
            }

        # Try LLM deep analysis first
        llm_result = _llm_analyze(text, all_papers)

        matches: list[dict] = []
        ai_analyzed = llm_result is not None
        sentence_risks: dict = {}

        if llm_result:
            overall_score = llm_result.get("overall_score", 0)
            overall_risk  = llm_result.get("overall_risk", "LOW")
            sentence_risks = llm_result.get("sentence_risks", {})
            summary_text   = llm_result.get("summary", "")

            for pa in (llm_result.get("papers") or []):
                idx = pa.get("paper_index", 1) - 1
                if 0 <= idx < len(all_papers):
                    p = all_papers[idx]
                    matches.append({
                        "title":             p.get("title", "Unknown"),
                        "authors":           p.get("authors", []),
                        "year":              p.get("year"),
                        "venue":             p.get("venue", ""),
                        "citation_count":    p.get("citation_count", 0),
                        "doi":               p.get("doi", ""),
                        "url":               p.get("url", ""),
                        "source":            p.get("source", ""),
                        "similarity_score":  pa.get("similarity_score", 0),
                        "risk_level":        pa.get("risk_level", "LOW"),
                        "overlapping_ideas": pa.get("overlapping_ideas", []),
                        "assessment":        pa.get("assessment", ""),
                        "matching_sentences":pa.get("matching_sentences", []),
                    })
        else:
            # Fallback: keyword scoring for all papers
            for p in all_papers:
                score = _keyword_score(text, p)
                if score >= 15:
                    risk = "HIGH" if score >= 60 else "MEDIUM" if score >= 30 else "LOW"
                    matches.append({
                        "title":             p.get("title", "Unknown"),
                        "authors":           p.get("authors", []),
                        "year":              p.get("year"),
                        "venue":             p.get("venue", ""),
                        "citation_count":    p.get("citation_count", 0),
                        "doi":               p.get("doi", ""),
                        "url":               p.get("url", ""),
                        "source":            p.get("source", ""),
                        "similarity_score":  score,
                        "risk_level":        risk,
                        "overlapping_ideas": [],
                        "assessment":        "Keyword overlap analysis (no LLM available).",
                        "matching_sentences":[],
                    })

            matches.sort(key=lambda x: x["similarity_score"], reverse=True)
            overall_score = matches[0]["similarity_score"] if matches else 0
            high = sum(1 for m in matches if m["risk_level"] == "HIGH")
            overall_risk = "HIGH" if high >= 2 or overall_score >= 70 else \
                           "MEDIUM" if overall_score >= 35 or high >= 1 else "LOW"
            summary_text = f"Keyword-based analysis. {len(matches)} overlapping papers found."

        matches.sort(key=lambda x: x["similarity_score"], reverse=True)

        # Annotate sentences with risk
        sentences = _split_sentences(text)
        sentence_data = []
        for i, s in enumerate(sentences):
            key = f"S{i+1}"
            risk = sentence_risks.get(key, "LOW") if ai_analyzed else "UNKNOWN"
            sentence_data.append({"id": key, "text": s, "risk": risk})

        provider_note = ""
        if not ai_analyzed:
            provider_note = " Set XAI_API_KEY / GROQ_API_KEY for AI-powered sentence analysis."

        return {
            "overall_risk":   overall_risk,
            "overall_score":  overall_score,
            "matches":        matches[:15],
            "papers_checked": len(all_papers),
            "input_length":   len(text.split()),
            "summary":        summary_text + provider_note,
            "ai_analyzed":    ai_analyzed,
            "sentences":      sentence_data,
        }
