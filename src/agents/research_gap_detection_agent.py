"""
Research Gap Detection Agent.

Primary mode ("llm"): builds a compact statistical summary of the analyzed
corpus (subtopic/method/dataset coverage, publication-year histogram,
unresolved contradictions) and asks an LLM for a small set of typed,
evidence-grounded gaps, each scored for importance and tractability. Only the
top-k ranked gaps are returned, so output no longer scales with rule firings.

Fallback mode ("rules"): the original keyword/threshold heuristics, kept as
the no-API-key fallback and the rule-based ablation baseline
(set GAP_MODE=rules), with output capped at top-k as well.

Gap types are standardized to:
  methodological | dataset | unexplored_subtopic | evaluation | contradiction_driven
"""
import json
import os
import re
from typing import List, Dict, Any, Optional
from collections import Counter, defaultdict
from datetime import datetime

from pydantic import BaseModel, Field

from ..models.data_models import TopicMap, Claim, ResearchGap, Contradiction, PaperMetadata
from .base_agent import BaseAgent
from . import llm_client

GAP_TYPES = ("methodological", "dataset", "unexplored_subtopic",
             "evaluation", "contradiction_driven")

# Legacy rule-based labels mapped onto the standardized taxonomy
_LEGACY_TYPE_MAP = {
    "unexplored_topic": "unexplored_subtopic",
    "underrepresented_method": "methodological",
    "methodological_gap": "methodological",
    "missing_dataset": "dataset",
    "evaluation_limitation": "evaluation",
    "evaluation_gap": "evaluation",
    "temporal_gap": "unexplored_subtopic",
}


class _GapItem(BaseModel):
    """Validated shape of one LLM-proposed gap."""
    description: str
    gap_type: str
    evidence: List[str] = []
    potential_questions: List[str] = []
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tractability: float = Field(default=0.5, ge=0.0, le=1.0)


class ResearchGapDetectionAgent(BaseAgent):
    """Agent responsible for identifying research gaps and opportunities."""

    def __init__(self, memory_store=None, mode: Optional[str] = None, top_k: int = 7):
        super().__init__("ResearchGapDetectionAgent", memory_store)
        self.mode = mode  # None = auto: "llm" if a provider is available
        self.top_k = top_k
        self.tracker: Optional[llm_client.UsageTracker] = None
        self.gap_detection_rules = self._initialize_gap_detection_rules()

    def _resolve_mode(self) -> str:
        mode = self.mode or os.getenv("GAP_MODE")
        if mode in ("llm", "rules"):
            return mode
        return "llm" if llm_client.get_provider() is not None else "rules"

    async def process(self, topic_map: TopicMap, claims: List[Claim],
                      contradictions: Optional[List[Contradiction]] = None,
                      papers: Optional[List[PaperMetadata]] = None) -> List[ResearchGap]:
        """
        Detect research gaps based on topic map and extracted claims.

        Args:
            topic_map: Structured topic information
            claims: List of extracted claims
            contradictions: Detected contradictions (seed contradiction_driven gaps)
            papers: Analyzed papers (enables real publication-year analysis)

        Returns:
            Top-k ranked research gaps
        """
        mode = self._resolve_mode()
        self.log_operation("research_gap_detection_start", {
            "subtopics": len(topic_map.subtopics),
            "claims": len(claims),
            "mode": mode,
        })

        if mode == "llm":
            try:
                gaps = self._llm_detect(topic_map, claims,
                                        contradictions or [], papers or [])
            except Exception as e:  # no provider available, or the call itself failed
                self.logger.warning(f"LLM gap detection unavailable ({e}); using rules")
                mode = "rules"
                gaps = self._rule_based_detect(topic_map, claims, papers or [])
        else:
            gaps = self._rule_based_detect(topic_map, claims, papers or [])

        # Low-evidence guard: with very few claims, gap statements are weak
        if len(claims) < 5:
            gaps = gaps[:2]
            for gap in gaps:
                note = f"Low-evidence: derived from only {len(claims)} extracted claims"
                if note not in gap.evidence:
                    gap.evidence.append(note)

        gaps = gaps[:self.top_k]
        for i, gap in enumerate(gaps):
            gap.rank = i + 1

        await self.store_result("research_gaps", gaps)

        self.log_operation("research_gap_detection_complete", {
            "total_gaps": len(gaps),
            "mode": mode,
        })

        return gaps

    # ------------------------------------------------------------------ #
    # LLM-based detection (primary)                                      #
    # ------------------------------------------------------------------ #

    def _build_corpus_summary(self, topic_map: TopicMap, claims: List[Claim],
                              contradictions: List[Contradiction],
                              papers: List[PaperMetadata]) -> str:
        lines = [f"Main topic: {topic_map.main_topic}"]

        subtopic_counts = {
            subtopic: sum(1 for c in claims
                          if subtopic.lower() in c.statement.lower())
            for subtopic in topic_map.subtopics
        }
        if subtopic_counts:
            lines.append("Claims per subtopic: " + ", ".join(
                f"{s}={n}" for s, n in subtopic_counts.items()))

        method_counts = {
            method: sum(1 for c in claims
                        if method.lower() in c.statement.lower())
            for method in topic_map.methods
        }
        if method_counts:
            lines.append("Claims per method: " + ", ".join(
                f"{m}={n}" for m, n in method_counts.items()))

        used_datasets = Counter(d for c in claims for d in c.datasets)
        lines.append("Datasets used in claims: " +
                     (", ".join(f"{d}({n})" for d, n in used_datasets.most_common(10))
                      or "none detected"))
        unused = set(topic_map.datasets) - set(used_datasets)
        if unused:
            lines.append("Expected datasets never used: " + ", ".join(sorted(unused)))

        if papers:
            year_hist = Counter(p.year for p in papers)
            lines.append("Papers per year: " + ", ".join(
                f"{y}={n}" for y, n in sorted(year_hist.items())))

        lines.append(f"Total claims: {len(claims)} from {len(papers) or 'unknown'} papers")

        if contradictions:
            lines.append(f"Unresolved contradictions ({len(contradictions)}):")
            for con in contradictions[:5]:
                lines.append(f"  - {con.explanation}")

        sample = [c.statement for c in claims[:15]]
        if sample:
            lines.append("Sample claims:")
            lines.extend(f"  - {s[:200]}" for s in sample)

        return "\n".join(lines)

    def _llm_detect(self, topic_map: TopicMap, claims: List[Claim],
                    contradictions: List[Contradiction],
                    papers: List[PaperMetadata]) -> List[ResearchGap]:
        summary = self._build_corpus_summary(topic_map, claims, contradictions, papers)

        prompt = (
            "You are analyzing the state of research on a topic based on the "
            "corpus statistics below. Identify the most important RESEARCH GAPS "
            "— things the literature has not adequately covered.\n\n"
            "Allowed gap_type values (choose the best fit):\n"
            "  methodological       — missing methods/practices (e.g. no ablations, no baselines)\n"
            "  dataset              — datasets missing, underused, or lacking diversity\n"
            "  unexplored_subtopic  — subtopics/settings with little or no work\n"
            "  evaluation           — missing evaluation styles (real-world, longitudinal, human)\n"
            "  contradiction_driven — unresolved conflicting findings needing resolution\n\n"
            "Return ONLY a JSON array of at most 10 objects with keys:\n"
            "  description (one clear sentence), gap_type, "
            "evidence (list of short strings citing the corpus statistics that "
            "support this gap), potential_questions (list of 2-3 research "
            "questions), importance (0.0-1.0), tractability (0.0-1.0: how "
            "feasible it is to address with current resources).\n"
            "Only propose gaps supported by the statistics; do not invent "
            "coverage numbers.\n\n"
            f"Corpus statistics:\n{summary}"
        )

        items = self._call_and_parse(prompt)
        if items is None:
            self.logger.warning("Gap LLM output unparseable; falling back to rules")
            return self._rule_based_detect(topic_map, claims, papers)

        gaps = []
        for item in items:
            gap_type = item.gap_type if item.gap_type in GAP_TYPES else "unexplored_subtopic"
            score = 0.6 * item.importance + 0.4 * item.tractability
            gaps.append(ResearchGap(
                description=item.description,
                gap_type=gap_type,
                related_topics=[topic_map.main_topic],
                potential_questions=item.potential_questions[:3],
                priority=round(score, 3),
                evidence=item.evidence[:5],
                score_components={
                    "importance": item.importance,
                    "tractability": item.tractability,
                },
                detection_method="llm",
            ))
        gaps.sort(key=lambda g: g.priority, reverse=True)
        return gaps

    def _call_and_parse(self, prompt: str) -> Optional[List[_GapItem]]:
        """Call the LLM and parse/validate its JSON, retrying once."""
        for attempt in range(2):
            raw = llm_client.chat(
                prompt,
                max_tokens=2048,
                temperature=0.0,
                tracker=self.tracker,
                purpose="gap_detection",
            ).strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            try:
                items = json.loads(raw)
                if isinstance(items, dict):
                    items = [items]
                return [_GapItem(**item) for item in items][:10]
            except Exception as e:
                if self.tracker is not None:
                    self.tracker.record_parse_failure("gap_detection")
                self.logger.warning(
                    f"Gap JSON parse failed (attempt {attempt + 1}): {e}")
        return None

    # ------------------------------------------------------------------ #
    # Rule-based detection (fallback + ablation baseline)                #
    # ------------------------------------------------------------------ #

    def _initialize_gap_detection_rules(self) -> Dict[str, Any]:
        """Initialize rules for detecting different types of research gaps."""
        return {
            "coverage_thresholds": {
                "subtopic_min_claims": 3,  # Minimum claims per subtopic
                "method_min_claims": 2,    # Minimum claims per method
                "dataset_min_papers": 2    # Minimum papers per dataset
            },
            "temporal_gaps": {
                "recent_years": 3,  # Consider papers from last 3 years as recent
                "min_recent_ratio": 0.3  # At least 30% of papers should be recent
            },
            "methodological_gaps": [
                "cross-validation", "ablation study", "statistical significance",
                "baseline comparison", "error analysis", "hyperparameter tuning"
            ],
            "evaluation_gaps": [
                "real-world evaluation", "user study", "clinical trial",
                "longitudinal study", "multi-domain evaluation"
            ]
        }

    def _rule_based_detect(self, topic_map: TopicMap, claims: List[Claim],
                           papers: List[PaperMetadata]) -> List[ResearchGap]:
        gaps: List[ResearchGap] = []
        gaps.extend(self._detect_coverage_gaps(topic_map, claims))
        gaps.extend(self._detect_methodological_gaps(claims))
        gaps.extend(self._detect_dataset_gaps(topic_map, claims))
        gaps.extend(self._detect_temporal_gaps(papers))
        gaps.extend(self._detect_evaluation_gaps(claims))

        for gap in gaps:
            gap.gap_type = _LEGACY_TYPE_MAP.get(gap.gap_type, gap.gap_type)
            gap.detection_method = "rules"

        return self._rank_gaps(gaps)

    def _detect_coverage_gaps(self, topic_map: TopicMap, claims: List[Claim]) -> List[ResearchGap]:
        """Detect gaps in topic coverage."""
        gaps = []

        # Analyze subtopic coverage
        subtopic_claims = defaultdict(list)
        for claim in claims:
            for subtopic in topic_map.subtopics:
                if subtopic.lower() in claim.statement.lower():
                    subtopic_claims[subtopic].append(claim)

        # Identify underexplored subtopics
        min_claims = self.gap_detection_rules["coverage_thresholds"]["subtopic_min_claims"]
        for subtopic in topic_map.subtopics:
            claim_count = len(subtopic_claims[subtopic])
            if claim_count < min_claims:
                gaps.append(ResearchGap(
                    description=f"Limited research on {subtopic}",
                    gap_type="unexplored_topic",
                    related_topics=[subtopic],
                    potential_questions=[
                        f"How does {subtopic} compare to other approaches?",
                        f"What are the limitations of current {subtopic} methods?",
                        f"Can {subtopic} be applied to new domains?"
                    ],
                    priority=self._calculate_priority(subtopic, claim_count, min_claims),
                    evidence=[f"Only {claim_count} of {len(claims)} claims mention this subtopic"],
                ))

        # Analyze method coverage
        method_claims = defaultdict(list)
        for claim in claims:
            for method in topic_map.methods:
                if method.lower() in claim.statement.lower():
                    method_claims[method].append(claim)

        min_method_claims = self.gap_detection_rules["coverage_thresholds"]["method_min_claims"]
        for method in topic_map.methods:
            claim_count = len(method_claims[method])
            if claim_count < min_method_claims:
                gaps.append(ResearchGap(
                    description=f"Insufficient evaluation of {method}",
                    gap_type="underrepresented_method",
                    related_topics=[method],
                    potential_questions=[
                        f"How effective is {method} compared to alternatives?",
                        f"What are the computational requirements of {method}?",
                        f"In which scenarios does {method} perform best?"
                    ],
                    priority=self._calculate_priority(method, claim_count, min_method_claims),
                    evidence=[f"Only {claim_count} of {len(claims)} claims mention this method"],
                ))

        return gaps

    def _detect_methodological_gaps(self, claims: List[Claim]) -> List[ResearchGap]:
        """Detect gaps in research methodology."""
        gaps = []

        total_claims = len(claims)
        for practice in self.gap_detection_rules["methodological_gaps"]:
            count = sum(1 for claim in claims
                        if practice.lower() in claim.statement.lower())
            coverage_ratio = count / total_claims if total_claims > 0 else 0

            if coverage_ratio < 0.2:  # Less than 20% coverage
                gaps.append(ResearchGap(
                    description=f"Limited use of {practice} in research",
                    gap_type="methodological_gap",
                    related_topics=[practice],
                    potential_questions=[
                        f"How would results change with proper {practice}?",
                        f"What are the best practices for {practice} in this domain?",
                        f"Why is {practice} not commonly used?"
                    ],
                    priority=0.8 - coverage_ratio,  # Higher priority for lower coverage
                    evidence=[f"{count} of {total_claims} claims mention {practice}"],
                ))

        return gaps

    def _detect_dataset_gaps(self, topic_map: TopicMap, claims: List[Claim]) -> List[ResearchGap]:
        """Detect gaps in dataset usage and availability."""
        gaps = []

        # Analyze dataset usage
        dataset_usage = Counter()
        for claim in claims:
            for dataset in claim.datasets:
                dataset_usage[dataset] += 1

        # Check if expected datasets are underused
        expected_datasets = set(topic_map.datasets)
        used_datasets = set(dataset_usage.keys())

        unused_datasets = expected_datasets - used_datasets
        for dataset in unused_datasets:
            gaps.append(ResearchGap(
                description=f"No research found using {dataset} dataset",
                gap_type="missing_dataset",
                related_topics=[dataset],
                potential_questions=[
                    f"How would methods perform on {dataset}?",
                    f"Is {dataset} suitable for current approaches?",
                    f"What challenges does {dataset} present?"
                ],
                priority=0.7,
                evidence=[f"{dataset} appears in the topic map but in no claim"],
            ))

        # Check for dataset diversity
        if len(used_datasets) < 3 and len(expected_datasets) > 3:
            gaps.append(ResearchGap(
                description="Limited dataset diversity in evaluation",
                gap_type="evaluation_limitation",
                related_topics=list(expected_datasets),
                potential_questions=[
                    "How do methods generalize across different datasets?",
                    "What are the domain-specific challenges?",
                    "Which datasets are most representative?"
                ],
                priority=0.6,
                evidence=[f"Only {len(used_datasets)} distinct datasets used across claims"],
            ))

        return gaps

    def _detect_temporal_gaps(self, papers: List[PaperMetadata]) -> List[ResearchGap]:
        """Detect temporal gaps using real publication years."""
        if not papers:
            return []

        rules = self.gap_detection_rules["temporal_gaps"]
        current_year = datetime.now().year
        recent = [p for p in papers
                  if current_year - p.year <= rules["recent_years"]]
        recent_ratio = len(recent) / len(papers)

        if recent_ratio >= rules["min_recent_ratio"]:
            return []

        return [ResearchGap(
            description="Few recent studies; the literature may be outdated",
            gap_type="temporal_gap",
            related_topics=["recent developments", "comparative analysis"],
            potential_questions=[
                "How do recent methods compare to established ones?",
                "Do older findings still hold with current techniques?",
            ],
            priority=0.5 + (rules["min_recent_ratio"] - recent_ratio),
            evidence=[
                f"Only {len(recent)} of {len(papers)} papers are from the last "
                f"{rules['recent_years']} years"
            ],
        )]

    def _detect_evaluation_gaps(self, claims: List[Claim]) -> List[ResearchGap]:
        """Detect gaps in evaluation practices."""
        gaps = []

        total_claims = len(claims)
        for eval_type in self.gap_detection_rules["evaluation_gaps"]:
            count = sum(1 for claim in claims
                        if eval_type.lower() in claim.statement.lower())
            coverage_ratio = count / total_claims if total_claims > 0 else 0

            if coverage_ratio < 0.1:  # Less than 10% coverage
                gaps.append(ResearchGap(
                    description=f"Lack of {eval_type} in research",
                    gap_type="evaluation_gap",
                    related_topics=[eval_type],
                    potential_questions=[
                        f"How would methods perform in {eval_type}?",
                        f"What are the challenges of conducting {eval_type}?",
                        f"What metrics are appropriate for {eval_type}?"
                    ],
                    priority=0.7,
                    evidence=[f"{count} of {total_claims} claims mention {eval_type}"],
                ))

        return gaps

    def _calculate_priority(self, topic: str, current_count: int, expected_count: int) -> float:
        """Calculate priority score for a research gap."""

        # Base priority on how far below expected the current count is
        deficit_ratio = (expected_count - current_count) / expected_count
        base_priority = min(deficit_ratio, 1.0)

        # Adjust based on topic importance (simplified)
        importance_keywords = [
            "neural", "deep", "learning", "optimization", "evaluation",
            "performance", "accuracy", "efficiency"
        ]

        importance_boost = 0.0
        for keyword in importance_keywords:
            if keyword in topic.lower():
                importance_boost += 0.1

        priority = min(base_priority + importance_boost, 1.0)
        return priority

    def _rank_gaps(self, gaps: List[ResearchGap]) -> List[ResearchGap]:
        """Rank research gaps by priority."""
        return sorted(gaps, key=lambda g: g.priority, reverse=True)

    def get_gap_summary(self, gaps: List[ResearchGap]) -> Dict[str, Any]:
        """Get summary statistics about research gaps."""

        if not gaps:
            return {"total": 0}

        by_type = Counter(gap.gap_type for gap in gaps)
        priorities = [gap.priority for gap in gaps]

        return {
            "total": len(gaps),
            "by_type": dict(by_type),
            "avg_priority": sum(priorities) / len(priorities),
            "high_priority": len([p for p in priorities if p > 0.7]),
            "medium_priority": len([p for p in priorities if 0.4 <= p <= 0.7]),
            "low_priority": len([p for p in priorities if p < 0.4]),
            "top_gaps": [
                {
                    "description": gap.description,
                    "type": gap.gap_type,
                    "priority": gap.priority
                }
                for gap in gaps[:5]
            ]
        }
