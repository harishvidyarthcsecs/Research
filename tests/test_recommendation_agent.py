import asyncio

from src.agents import llm_client
from src.agents.recommendation_agent import RecommendationAgent
from src.models.data_models import (
    Claim, Contradiction, PaperMetadata, ResearchGap, TopicMap,
)


def _topic():
    return TopicMap(main_topic="Graph learning", subtopics=["robustness"])


def _paper():
    return PaperMetadata(
        id="p1", title="Reliable Graph Models", authors=["A. Author"], year=2025,
        venue="Test Journal", abstract="A robustness study.", relevance_score=0.9,
    )


def _claim():
    return Claim(id="c1", statement="Robustness varies across datasets.", paper_id="p1")


def _gap():
    return ResearchGap(
        id="g1", description="Cross-dataset evaluation is missing", gap_type="evaluation",
        potential_questions=["How well do models transfer across datasets?"],
        priority=0.8, evidence=["Only one dataset was evaluated"],
        score_components={"importance": 0.9, "tractability": 0.7},
    )


def _contradiction():
    return Contradiction(
        id="x1", claim1_id="c1", claim2_id="c2", contradiction_type="conditional",
        explanation="Reported robustness differs by evaluation setting.", severity=0.7,
        evidence_claim1="Robust under noise.", evidence_claim2="Fails under noise.",
        paper1_id="p1", paper2_id="p2",
    )


def test_rules_mode_returns_ranked_recommendations():
    recommendations, summary = asyncio.run(RecommendationAgent(mode="rules").process(
        _topic(), [_claim()], [_contradiction()], [_gap()], [_paper()]
    ))
    assert recommendations
    assert summary
    assert [item.rank for item in recommendations] == list(range(1, len(recommendations) + 1))
    assert all(item.detection_method == "rules" for item in recommendations)
    assert [item.priority for item in recommendations] == sorted(
        [item.priority for item in recommendations], reverse=True
    )


def test_all_empty_returns_one_safe_fallback():
    recommendations, summary = asyncio.run(RecommendationAgent(mode="rules").process(
        _topic(), [], [], [], []
    ))
    assert len(recommendations) == 1
    assert recommendations[0].linked_gap_ids == []
    assert recommendations[0].linked_paper_ids == []
    assert recommendations[0].rank == 1
    assert summary


def test_llm_json_parses_scores_and_ranks(monkeypatch):
    def fake_chat(*args, **kwargs):
        return """{
          "executive_summary": "Focus on robust evaluation.",
          "recommendations": [
            {"category": "reading", "title": "Read first", "rationale": "Relevant",
             "action": "Review p1", "supporting_evidence": ["High relevance"],
             "linked_gap_ids": [], "linked_paper_ids": ["p1"],
             "importance": 0.6, "tractability": 0.8},
            {"category": "experiment", "title": "Run transfer study", "rationale": "Gap g1",
             "action": "Evaluate transfer", "supporting_evidence": ["One dataset"],
             "linked_gap_ids": ["g1", "invented"], "linked_paper_ids": [],
             "importance": 0.95, "tractability": 0.7}
          ]
        }"""

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    recommendations, summary = asyncio.run(RecommendationAgent(mode="llm").process(
        _topic(), [_claim()], [], [_gap()], [_paper()]
    ))
    assert summary == "Focus on robust evaluation."
    assert [item.rank for item in recommendations] == [1, 2]
    assert recommendations[0].title == "Run transfer study"
    assert recommendations[0].linked_gap_ids == ["g1"]
    assert all(item.detection_method == "llm" for item in recommendations)


def test_malformed_llm_json_falls_back_and_records_failure(monkeypatch):
    tracker = llm_client.UsageTracker()
    agent = RecommendationAgent(mode="llm")
    agent.tracker = tracker
    monkeypatch.setattr(llm_client, "chat", lambda *args, **kwargs: "not json")

    recommendations, summary = asyncio.run(agent.process(
        _topic(), [_claim()], [], [_gap()], [_paper()]
    ))
    assert recommendations
    assert summary
    assert all(item.detection_method == "rules" for item in recommendations)
    assert tracker.summary()["parse_failures"] == 1
    assert tracker.summary()["by_purpose"]["recommendations"]["parse_failures"] == 1
