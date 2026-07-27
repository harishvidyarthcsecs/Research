"""
Unit tests for the evaluation harness and the upgraded detection agents:
matching logic, UsageTracker cost accounting, candidate-pair retrieval, and
the LLM JSON-repair / fallback paths (LLM calls mocked).
"""
import asyncio
import json
from unittest.mock import patch

import pytest

from eval import matching
from src.agents import llm_client
from src.agents.candidate_pair_retriever import retrieve_candidate_pairs
from src.agents.contradiction_detection_agent import ContradictionDetectionAgent
from src.agents.research_gap_detection_agent import ResearchGapDetectionAgent
from src.models.data_models import Claim, TopicMap


# --------------------------------------------------------------------- #
# matching.py                                                           #
# --------------------------------------------------------------------- #

def test_match_claims_fuzzy_same_paper():
    pred = [{"paper_id": "p1", "statement": "GNNs improve accuracy by 15 percent"},
            {"paper_id": "p2", "statement": "unrelated statement"}]
    gold = [{"paper_id": "p1", "statement": "GNNs improve accuracy by 15%"}]
    result = matching.match_claims(pred, gold)
    assert result["tp"] == 1
    assert result["fp"] == 1
    assert result["recall"] == 1.0
    assert 0 < result["precision"] < 1


def test_match_claims_wrong_paper_no_match():
    pred = [{"paper_id": "pX", "statement": "GNNs improve accuracy by 15%"}]
    gold = [{"paper_id": "p1", "statement": "GNNs improve accuracy by 15%"}]
    result = matching.match_claims(pred, gold)
    assert result["tp"] == 0
    assert result["recall"] == 0.0


def test_match_contradictions_positive_and_hard_negative():
    pred = [
        {"paper1_id": "p1", "paper2_id": "p2",
         "evidence_claim1": "A wins", "evidence_claim2": "A loses"},
        {"paper1_id": "p3", "paper2_id": "p4"},  # hits a gold negative
    ]
    gold = {
        "positives": [{"paper_id_1": "p1", "paper_id_2": "p2",
                       "claim_text_1": "A wins", "claim_text_2": "A loses"}],
        "negatives": [{"paper_id_1": "p3", "paper_id_2": "p4"}],
    }
    result = matching.match_contradictions(pred, gold)
    pair = result["pair_level"]
    assert pair["tp"] == 1
    assert pair["fp_on_negatives"] == 1
    assert pair["recall"] == 1.0
    assert pair["false_positive_rate_on_negatives"] == 1.0
    assert result["claim_level_strict"]["tp"] == 1


def test_match_contradictions_unordered_pairs():
    """Paper pair should match regardless of ordering."""
    pred = [{"paper1_id": "p2", "paper2_id": "p1"}]
    gold = {"positives": [{"paper_id_1": "p1", "paper_id_2": "p2"}], "negatives": []}
    assert matching.match_contradictions(pred, gold)["pair_level"]["tp"] == 1


def test_match_gaps_precision_at_k_and_keywords():
    pred = [{"description": "No study uses QM9 dataset", "gap_type": "dataset"},
            {"description": "irrelevant", "gap_type": "evaluation"}]
    gold = [{"description": "QM9 is never evaluated", "gap_type": "dataset",
             "keywords": ["QM9", "dataset"]}]
    result = matching.match_gaps(pred, gold, ks=(3,))
    assert result["recall"] == 1.0
    assert result["precision_at_3"] == pytest.approx(0.5)


def test_match_gaps_type_mismatch_blocks():
    pred = [{"description": "QM9 is never evaluated", "gap_type": "evaluation"}]
    gold = [{"description": "QM9 is never evaluated", "gap_type": "dataset",
             "keywords": ["QM9"]}]
    result = matching.match_gaps(pred, gold, ks=(3,))
    assert result["recall"] == 0.0


# --------------------------------------------------------------------- #
# UsageTracker                                                          #
# --------------------------------------------------------------------- #

def test_usage_tracker_accumulates_and_prices():
    tracker = llm_client.UsageTracker()
    tracker.record("xai", "grok-3-mini", 1000, 500, purpose="claim_extraction")
    tracker.record("xai", "grok-3-mini", 2000, 1000, purpose="contradiction_judge")
    tracker.record_parse_failure("contradiction_judge")
    summary = tracker.summary()
    assert summary["calls"] == 2
    assert summary["prompt_tokens"] == 3000
    assert summary["completion_tokens"] == 1500
    assert summary["parse_failures"] == 1
    # grok-3-mini priced at (0.30, 0.50) per Mtok
    expected = (3000 * 0.30 + 1500 * 0.50) / 1_000_000
    assert summary["estimated_cost_usd"] == pytest.approx(round(expected, 6))
    assert summary["by_purpose"]["contradiction_judge"]["parse_failures"] == 1


def test_usage_tracker_unknown_model_is_free():
    tracker = llm_client.UsageTracker()
    tracker.record("local", "some-unknown-model", 5000, 5000)
    assert tracker.summary()["estimated_cost_usd"] == 0.0


# --------------------------------------------------------------------- #
# candidate_pair_retriever                                              #
# --------------------------------------------------------------------- #

def test_retriever_excludes_same_paper_and_ranks():
    claims = [
        Claim(id="c1", statement="GNNs improve drug discovery accuracy on ChEMBL",
              paper_id="p1", datasets=["ChEMBL"]),
        Claim(id="c2", statement="GNNs decrease drug discovery accuracy on ChEMBL",
              paper_id="p2", datasets=["ChEMBL"]),
        Claim(id="c3", statement="GNNs improve drug discovery accuracy on ChEMBL",
              paper_id="p1"),  # same paper as c1 -> excluded
        Claim(id="c4", statement="Transformers dominate protein folding", paper_id="p3"),
    ]
    pairs = retrieve_candidate_pairs(claims, top_k=10)
    paper_pairs = {frozenset({a.paper_id, b.paper_id}) for a, b, _ in pairs}
    assert frozenset({"p1"}) not in paper_pairs  # no same-paper pair
    # the near-identical opposite claims should be the top candidate
    top_a, top_b, _ = pairs[0]
    assert {top_a.id, top_b.id} == {"c1", "c2"}


def test_retriever_handles_too_few_claims():
    assert retrieve_candidate_pairs([], top_k=5) == []
    assert retrieve_candidate_pairs([Claim(id="c1", statement="x", paper_id="p1")]) == []


# --------------------------------------------------------------------- #
# LLM JSON-repair / fallback paths (mocked chat)                       #
# --------------------------------------------------------------------- #

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_contradiction_judge_parses_and_thresholds():
    claims = [
        Claim(id="c1", statement="Method A improves accuracy on ChEMBL",
              paper_id="p1", datasets=["ChEMBL"]),
        Claim(id="c2", statement="Method A reduces accuracy on ChEMBL",
              paper_id="p2", datasets=["ChEMBL"]),
    ]
    good = json.dumps([{"pair": 1, "likert": 10, "verdict": "contradiction",
                        "contradiction_type": "conditional",
                        "explanation": "opposite effect on ChEMBL",
                        "evidence_1": "improves accuracy",
                        "evidence_2": "reduces accuracy"}])
    agent = ContradictionDetectionAgent(mode="llm", likert_threshold=8)
    with patch("src.agents.contradiction_detection_agent.llm_client.chat",
               return_value=good):
        out = _run(agent.process(claims))
    assert len(out) == 1
    assert out[0].likert_score == 10
    assert out[0].detection_method == "llm_judge"
    assert out[0].severity == pytest.approx((10 - 6) / 5)


def test_contradiction_judge_below_threshold_emits_nothing():
    claims = [
        Claim(id="c1", statement="Method A improves accuracy on ChEMBL", paper_id="p1"),
        Claim(id="c2", statement="Method A also studied on ChEMBL", paper_id="p2"),
    ]
    supportive = json.dumps([{"pair": 1, "likert": 3, "verdict": "support",
                              "explanation": "compatible"}])
    agent = ContradictionDetectionAgent(mode="llm", likert_threshold=8)
    with patch("src.agents.contradiction_detection_agent.llm_client.chat",
               return_value=supportive):
        out = _run(agent.process(claims))
    assert out == []


def test_contradiction_judge_json_repair_falls_back_per_pair():
    claims = [
        Claim(id="c1", statement="Method A improves accuracy on ChEMBL", paper_id="p1"),
        Claim(id="c2", statement="Method A reduces accuracy on ChEMBL", paper_id="p2"),
    ]
    tracker = llm_client.UsageTracker()
    agent = ContradictionDetectionAgent(mode="llm", likert_threshold=8)
    agent.tracker = tracker
    # Always return garbage -> both batched attempts and per-pair retries fail
    with patch("src.agents.contradiction_detection_agent.llm_client.chat",
               return_value="not json at all"):
        out = _run(agent.process(claims))
    assert out == []
    assert tracker.summary()["parse_failures"] >= 1


def test_gap_agent_json_repair_falls_back_to_rules():
    tm = TopicMap(main_topic="GNNs in drug discovery",
                  subtopics=["property prediction"], methods=["GCN"],
                  datasets=["ChEMBL", "QM9", "ZINC", "PubChem"])
    claims = [Claim(id=f"c{i}", statement=f"GCN result {i}", paper_id=f"p{i}")
              for i in range(6)]
    agent = ResearchGapDetectionAgent(mode="llm", top_k=7)
    with patch("src.agents.research_gap_detection_agent.llm_client.chat",
               return_value="garbage not json"):
        gaps = _run(agent.process(tm, claims))
    # Falls back to rules; still returns ranked gaps rather than crashing
    assert all(g.detection_method == "rules" for g in gaps)
    assert all(g.rank is not None for g in gaps)


def test_gap_agent_low_evidence_guard():
    tm = TopicMap(main_topic="x", subtopics=["a"], methods=["m"], datasets=["d"])
    claims = [Claim(id="c1", statement="only one claim", paper_id="p1")]
    agent = ResearchGapDetectionAgent(mode="rules", top_k=7)
    gaps = _run(agent.process(tm, claims))
    assert len(gaps) <= 2
    assert any("Low-evidence" in e for g in gaps for e in g.evidence)
