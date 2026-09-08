from datetime import datetime

from src.models.data_models import (
    Citation, PaperMetadata, Recommendation, ResearchResults, TopicMap,
)
from src.reporting.report_builder import (
    LEGACY_REPORT_KEYS, build_report_dict, detect_run_mode, render_markdown,
)


def _results(provider=None, calls=0, parse_failures=0):
    paper = PaperMetadata(
        id="p1", title="A Useful Paper", authors=["A. Author"], year=2025,
        venue="Journal", abstract="Evidence.", relevance_score=0.9,
    )
    return ResearchResults(
        topic_map=TopicMap(
            main_topic="Test Topic", subtopics=["Subtopic"], methods=["Method"],
            datasets=["Dataset"], keywords=["keyword"],
        ),
        papers=[paper], claims=[], contradictions=[], research_gaps=[],
        citations=[Citation(paper_id="p1", bibtex="@article{x}", apa="APA", ieee="IEEE")],
        recommendations=[Recommendation(
            id="r1", category="reading", title="Read it", rationale="Relevant",
            action="Review the paper", supporting_evidence=["High relevance"],
            linked_paper_ids=["p1"], priority=0.9, rank=1,
        )],
        executive_summary="A concise synthesis.", generated_at=datetime(2026, 1, 1),
        total_papers_analyzed=1, total_claims_extracted=0,
        run_metadata={"provider": provider, "model": "model", "duration_s": 1.5},
        usage={"calls": calls, "parse_failures": parse_failures},
    )


def test_build_report_is_strict_superset_of_legacy_schema():
    report = build_report_dict(_results())
    assert LEGACY_REPORT_KEYS < set(report)
    assert {"run_mode", "executive_summary", "recommendations", "reading_list"} <= set(report)
    assert report["recommendations"][0]["title"] == "Read it"
    assert report["reading_list"][0]["paper_id"] == "p1"


def test_detect_run_mode_degraded_llm_and_rules():
    assert detect_run_mode(_results(provider="xai", calls=0))["mode"] == "degraded"
    assert detect_run_mode(_results(provider="xai", calls=2))["mode"] == "llm"
    assert detect_run_mode(_results(provider=None, calls=0))["mode"] == "rules"
    assert detect_run_mode(_results(provider="xai", calls=2, parse_failures=2))["mode"] == "degraded"


def test_markdown_sections_and_degraded_banner():
    degraded = render_markdown(build_report_dict(_results(provider="xai", calls=0)))
    for header in (
        "# Test Topic", "## Executive Summary", "## Topic Map",
        "## Recommended Reading", "## AI Recommendations", "## Key Claims",
        "## Contradictions", "## Research Gaps", "## Citations",
        "## Methodology & Limitations",
    ):
        assert header in degraded
    assert "**DEGRADED MODE:**" in degraded

    llm = render_markdown(build_report_dict(_results(provider="xai", calls=2)))
    assert "**DEGRADED MODE:**" not in llm
