"""Canonical JSON and Markdown reporting for CLI and web research runs."""
from collections import defaultdict
from typing import Any, Dict
import re
import time


LEGACY_REPORT_KEYS = {
    "topic", "generated_at", "summary", "usage", "run_metadata", "topic_map",
    "papers", "claims", "contradictions", "research_gaps", "citations",
}


def detect_run_mode(results) -> dict:
    """Describe whether a run used an LLM, rules, or silently degraded."""
    metadata = getattr(results, "run_metadata", {}) or {}
    usage = getattr(results, "usage", {}) or {}
    provider = metadata.get("provider")
    calls = int(usage.get("calls") or 0)
    parse_failures = int(usage.get("parse_failures") or 0)

    if not provider:
        return {
            "mode": "rules",
            "reason": "No LLM provider was configured; deterministic rules were used.",
        }
    if calls == 0:
        return {
            "mode": "degraded",
            "reason": f"Provider {provider} was configured but no successful LLM calls were recorded.",
        }
    if parse_failures >= calls:
        return {
            "mode": "degraded",
            "reason": (
                f"Provider {provider} was used, but {parse_failures} parse failures "
                f"were recorded across {calls} calls."
            ),
        }
    return {
        "mode": "llm",
        "reason": f"Provider {provider} completed {calls} tracked LLM calls.",
    }


def _model_dict(value) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()


def build_report_dict(results) -> dict:
    """Build the canonical web/CLI result payload."""
    papers = [
        {
            "title": paper.title,
            "authors": paper.authors,
            "year": paper.year,
            "venue": paper.venue,
            "relevance_score": paper.relevance_score,
            "abstract": paper.abstract[:300] + "..." if len(paper.abstract) > 300 else paper.abstract,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "url": paper.url,
        }
        for paper in results.papers
    ]
    recommendations = [
        _model_dict(item) for item in getattr(results, "recommendations", [])
    ]
    reading_list = []
    for rank, paper in enumerate(sorted(
        results.papers, key=lambda item: item.relevance_score, reverse=True
    ), 1):
        reading_list.append({
            "rank": rank,
            "paper_id": paper.id,
            "title": paper.title,
            "authors": paper.authors,
            "year": paper.year,
            "venue": paper.venue,
            "relevance_score": paper.relevance_score,
            "url": _get_paper_url(paper),
            "why": (
                f"Ranked #{rank} by corpus relevance "
                f"({max(0.0, min(1.0, paper.relevance_score)):.0%})."
            ),
        })

    return {
        "topic": results.topic_map.main_topic,
        "generated_at": results.generated_at.isoformat(),
        "summary": {
            "papers_analyzed": results.total_papers_analyzed,
            "claims_extracted": results.total_claims_extracted,
            "contradictions_found": len(results.contradictions),
            "research_gaps_identified": len(results.research_gaps),
        },
        "usage": results.usage,
        "run_metadata": results.run_metadata,
        "topic_map": {
            "main_topic": results.topic_map.main_topic,
            "subtopics": results.topic_map.subtopics,
            "methods": results.topic_map.methods,
            "keywords": results.topic_map.keywords,
            "datasets": results.topic_map.datasets,
        },
        "papers": papers,
        "claims": [
            {
                "statement": claim.statement,
                "confidence": claim.confidence,
                "metrics": claim.metrics,
                "datasets": claim.datasets,
                "conditions": claim.conditions,
            }
            for claim in results.claims
        ],
        "contradictions": [
            {
                "explanation": contradiction.explanation,
                "type": contradiction.contradiction_type,
                "severity": contradiction.severity,
                "likert_score": contradiction.likert_score,
                "verdict": contradiction.verdict,
                "evidence_claim1": contradiction.evidence_claim1,
                "evidence_claim2": contradiction.evidence_claim2,
                "paper1_id": contradiction.paper1_id,
                "paper2_id": contradiction.paper2_id,
                "detection_method": contradiction.detection_method,
            }
            for contradiction in results.contradictions
        ],
        "research_gaps": [
            {
                "description": gap.description,
                "type": gap.gap_type,
                "priority": gap.priority,
                "potential_questions": gap.potential_questions,
                "evidence": gap.evidence,
                "rank": gap.rank,
                "detection_method": gap.detection_method,
            }
            for gap in results.research_gaps
        ],
        "citations": [
            {
                "paper_id": citation.paper_id,
                "bibtex": citation.bibtex,
                "apa": citation.apa,
                "ieee": citation.ieee,
                "mla": citation.mla if hasattr(citation, "mla") else None,
                "custom_format": _generate_custom_citation(paper),
                "paper_url": _get_paper_url(paper),
                "journal_name": paper.venue,
                "year": paper.year,
            }
            for citation, paper in zip(results.citations, results.papers)
        ],
        "run_mode": detect_run_mode(results),
        "executive_summary": getattr(results, "executive_summary", ""),
        "recommendations": recommendations,
        "reading_list": reading_list,
    }


def render_markdown(report: dict) -> str:
    """Render a canonical report dictionary as readable Markdown."""
    metadata = report.get("run_metadata") or {}
    run_mode = report.get("run_mode") or {"mode": "rules", "reason": "Unknown run mode."}
    meta_parts = [
        f"Provider: {metadata.get('provider') or 'none'}",
        f"Model: {metadata.get('model') or 'none'}",
        f"Duration: {metadata.get('duration_s', 0)}s",
        f"Generated: {report.get('generated_at', '')}",
    ]
    lines = [f"# {report.get('topic') or 'Research Report'}", "", " · ".join(meta_parts), ""]
    if run_mode.get("mode") != "llm":
        label = "DEGRADED MODE" if run_mode.get("mode") == "degraded" else "RULE-BASED MODE"
        lines.extend([f"> **{label}:** {run_mode.get('reason', '')}", ""])

    lines.extend(["## Executive Summary", "", report.get("executive_summary") or "No executive summary was generated.", ""])

    topic_map = report.get("topic_map") or {}
    lines.extend(["## Topic Map", ""])
    for label, key in (("Subtopics", "subtopics"), ("Methods", "methods"),
                       ("Datasets", "datasets"), ("Keywords", "keywords")):
        values = topic_map.get(key) or []
        lines.append(f"- **{label}:** {', '.join(str(v) for v in values) or 'None identified'}")
    lines.append("")

    lines.extend(["## Recommended Reading", ""])
    reading = report.get("reading_list") or []
    if not reading:
        lines.append("No papers were available for ranking.")
    for item in reading:
        authors = ", ".join(item.get("authors") or [])
        link = f" ([link]({item['url']}))" if item.get("url") else ""
        lines.extend([
            f"{item.get('rank', '-')}. **{item.get('title', 'Untitled')}**{link}",
            f"   - {authors} · {item.get('year', '')} · {item.get('venue', '')}",
            f"   - Why: {item.get('why', '')}",
        ])
    lines.append("")

    lines.extend(["## AI Recommendations", ""])
    grouped = defaultdict(list)
    for item in report.get("recommendations") or []:
        grouped[item.get("category") or "other"].append(item)
    if not grouped:
        lines.append("No recommendations were generated.")
    for category, items in grouped.items():
        lines.extend([f"### {category.replace('_', ' ').title()}", ""])
        for item in items:
            lines.append(f"{item.get('rank', '-')}. **{item.get('title', '')}** — {float(item.get('priority') or 0):.0%} priority")
            lines.append(f"   - Rationale: {item.get('rationale', '')}")
            lines.append(f"   - Action: {item.get('action', '')}")
            evidence = item.get("supporting_evidence") or []
            if evidence:
                lines.append(f"   - Evidence: {'; '.join(str(value) for value in evidence)}")
        lines.append("")

    lines.extend(["## Key Claims", ""])
    claims = sorted(report.get("claims") or [], key=lambda item: item.get("confidence") or 0, reverse=True)[:10]
    if not claims:
        lines.append("No claims were extracted.")
    for claim in claims:
        lines.append(f"- **{float(claim.get('confidence') or 0):.0%} confidence:** {claim.get('statement', '')}")
    lines.append("")

    lines.extend(["## Contradictions", ""])
    contradictions = report.get("contradictions") or []
    if not contradictions:
        lines.append("No contradictions were detected.")
    for item in contradictions:
        lines.append(f"- **{item.get('type', 'unspecified')}** (Likert: {item.get('likert_score') or 'n/a'}): {item.get('explanation', '')}")
        evidence = [v for v in (item.get("evidence_claim1"), item.get("evidence_claim2")) if v]
        if evidence:
            lines.append(f"  - Evidence: {' / '.join(evidence)}")
    lines.append("")

    lines.extend(["## Research Gaps", ""])
    gaps = sorted(report.get("research_gaps") or [], key=lambda item: item.get("priority") or 0, reverse=True)
    if not gaps:
        lines.append("No research gaps were identified.")
    for gap in gaps:
        lines.append(f"{gap.get('rank') or '-'}. **{gap.get('type', 'gap')}** — {float(gap.get('priority') or 0):.0%}: {gap.get('description', '')}")
        for question in gap.get("potential_questions") or []:
            lines.append(f"   - {question}")
    lines.append("")

    lines.extend(["## Citations", ""])
    citations = report.get("citations") or []
    if not citations:
        lines.append("No citations were generated.")
    for citation in citations:
        lines.append(f"- {citation.get('custom_format') or citation.get('apa') or ''}")
    lines.append("")

    summary = report.get("summary") or {}
    lines.extend(["## Methodology & Limitations", ""])
    lines.append(
        f"This report analyzed {summary.get('papers_analyzed', 0)} papers, extracted "
        f"{summary.get('claims_extracted', 0)} claims, found "
        f"{summary.get('contradictions_found', 0)} contradictions, and identified "
        f"{summary.get('research_gaps_identified', 0)} research gaps."
    )
    lines.append(f"Run mode: **{run_mode.get('mode', 'unknown')}** — {run_mode.get('reason', '')}")
    if metadata.get("frozen_corpus"):
        lines.append("The run used a frozen corpus; paper discovery was skipped for reproducibility.")
    else:
        lines.append("Findings are limited to retrieved titles and abstracts and may omit inaccessible literature.")
    return "\n".join(lines).rstrip() + "\n"


def _generate_custom_citation(paper):
    """Generate the legacy custom citation format with verified metadata."""
    citation = (
        f"\\bibitem{{{_generate_bibitem_key(paper)}}} "
        f"{_format_authors_custom(paper.authors)}, {_format_title_custom(paper.title)}, "
        f"{paper.venue}"
    )
    volume_info = _extract_volume_info_crossref(paper)
    if volume_info["volume"]:
        citation += f" \\textbf{{{volume_info['volume']}}}"
        if volume_info["issue"]:
            citation += f"({volume_info['issue']})"
    citation += f" ({paper.year})"
    if volume_info["pages"]:
        citation += f" {volume_info['pages']}"
    paper_url = _get_paper_url(paper)
    if paper_url:
        citation += f". {paper_url}"
    return citation


def _extract_volume_info_crossref(paper):
    """Extract real volume, issue, and page information from CrossRef or venue."""
    volume_info = {"volume": None, "issue": None, "pages": None, "article_number": None}
    if paper.doi:
        try:
            import requests
            doi = paper.doi.strip()
            for prefix in ("https://doi.org/", "http://dx.doi.org/", "doi:"):
                if doi.startswith(prefix):
                    doi = doi[len(prefix):]
                    break
            response = requests.get(
                f"https://api.crossref.org/works/{doi}",
                headers={
                    "User-Agent": "Research System/1.0 (mailto:research@example.com)",
                    "Accept": "application/json",
                },
                timeout=10,
            )
            if response.status_code == 200:
                work = response.json().get("message", {})
                if work.get("volume"):
                    volume_info["volume"] = str(work["volume"]).strip()
                if work.get("issue"):
                    volume_info["issue"] = str(work["issue"]).strip()
                if work.get("page"):
                    volume_info["pages"] = str(work["page"]).strip()
                elif work.get("article-number"):
                    article_number = str(work["article-number"]).strip()
                    volume_info["article_number"] = article_number
                    volume_info["pages"] = article_number
                time.sleep(0.1)
        except Exception:
            pass
    if not any((volume_info["volume"], volume_info["issue"], volume_info["pages"])) and paper.venue:
        venue = paper.venue.lower()
        volume = re.search(r"vol(?:ume)?\.?\s*(\d+)", venue)
        issue = re.search(r"(?:no|issue)\.?\s*(\d+)", venue)
        combined = re.search(r"(\d+)\((\d+)\)", venue)
        if volume:
            volume_info["volume"] = volume.group(1)
        if issue:
            volume_info["issue"] = issue.group(1)
        if combined:
            volume_info["volume"], volume_info["issue"] = combined.groups()
    return volume_info


def _generate_bibitem_key(paper):
    if not paper.authors:
        return f"Unknown{paper.year % 100:02d}"
    authors = paper.authors[:3] if len(paper.authors) >= 3 else paper.authors[:2]
    key_parts = []
    for author in authors:
        last_name = author.split()[-1] if author.split() else author
        if len(last_name) >= 2:
            key_parts.append(last_name[:2].title())
        elif len(last_name) == 1:
            key_parts.append(last_name.upper())
    return "".join(key_parts) + f"{paper.year % 100:02d}"


def _format_authors_custom(authors):
    if not authors:
        return "Unknown Author"
    formatted = []
    for author in authors:
        parts = author.strip().split()
        if len(parts) < 2 or (len(parts) == 2 and len(parts[0]) <= 4 and "." in parts[0]):
            formatted.append(author.strip())
            continue
        initials = [name if name.endswith(".") else f"{name[0].upper()}."
                    for name in parts[:-1] if name and name[0].isalpha()]
        formatted.append(f"{''.join(initials)} {parts[-1]}" if initials else parts[-1])
    return ", ".join(formatted)


def _format_title_custom(title):
    if not title:
        return ""
    value = title.strip().removesuffix(".").lower()
    value = value[0].upper() + value[1:] if value else value
    proper_nouns = (
        "wiener", "euler", "hamilton", "fibonacci", "pascal", "newton", "gauss",
        "fourier", "laplace", "bayes", "markov", "poisson", "bernoulli", "covid",
        "sars", "hiv", "aids", "dna", "rna", "pcr", "crispr",
    )
    for noun in proper_nouns:
        value = re.sub(r"\b" + re.escape(noun) + r"\b", noun.capitalize(), value, flags=re.IGNORECASE)
    return value


def _get_paper_url(paper):
    if paper.doi:
        return paper.doi if paper.doi.startswith("http") else f"https://doi.org/{paper.doi}"
    if paper.url:
        return paper.url
    if paper.arxiv_id:
        return f"https://arxiv.org/abs/{paper.arxiv_id}"
    return ""
