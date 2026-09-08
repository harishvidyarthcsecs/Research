"""Actionable, evidence-linked recommendations for a completed research run."""
import json
import os
import re
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from ..models.data_models import (
    Claim,
    Contradiction,
    PaperMetadata,
    Recommendation,
    ResearchGap,
    TopicMap,
)
from . import llm_client
from .base_agent import BaseAgent


RECOMMENDATION_CATEGORIES = (
    "next_step", "reading", "experiment", "method_adoption", "risk"
)


class _RecItem(BaseModel):
    """Validated shape of one LLM-proposed recommendation."""
    category: str
    title: str
    rationale: str
    action: str = ""
    supporting_evidence: List[str] = []
    linked_gap_ids: List[str] = []
    linked_paper_ids: List[str] = []
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tractability: float = Field(default=0.5, ge=0.0, le=1.0)


class RecommendationAgent(BaseAgent):
    """Turn papers and findings into a concise ranked action plan."""

    def __init__(self, memory_store=None, mode=None, top_k=8):
        super().__init__("RecommendationAgent", memory_store)
        self.mode = mode
        self.top_k = top_k
        self.tracker: Optional[llm_client.UsageTracker] = None

    def _resolve_mode(self) -> str:
        mode = self.mode or os.getenv("RECOMMENDATION_MODE")
        if mode in ("llm", "rules"):
            return mode
        return "llm" if llm_client.get_provider() is not None else "rules"

    async def process(
        self,
        topic_map: TopicMap,
        claims: List[Claim],
        contradictions: List[Contradiction],
        research_gaps: List[ResearchGap],
        papers: List[PaperMetadata],
    ) -> Tuple[List[Recommendation], str]:
        mode = self._resolve_mode()
        self.log_operation("recommendation_generation_start", {
            "claims": len(claims),
            "contradictions": len(contradictions),
            "gaps": len(research_gaps),
            "papers": len(papers),
            "mode": mode,
        })

        # With no findings there is nothing safe for an LLM to link to.
        if not claims and not contradictions and not research_gaps:
            recommendations, summary = self._rule_based_generate(
                topic_map, claims, contradictions, research_gaps, papers
            )
            mode = "rules"
        elif mode == "llm":
            try:
                generated = self._llm_generate(
                    topic_map, claims, contradictions, research_gaps, papers
                )
            except Exception as exc:
                self.logger.warning(
                    f"LLM recommendation generation unavailable ({exc}); using rules"
                )
                generated = None
            if generated is None:
                mode = "rules"
                recommendations, summary = self._rule_based_generate(
                    topic_map, claims, contradictions, research_gaps, papers
                )
            else:
                recommendations, summary = generated
        else:
            recommendations, summary = self._rule_based_generate(
                topic_map, claims, contradictions, research_gaps, papers
            )

        recommendations.sort(key=lambda item: item.priority, reverse=True)
        recommendations = recommendations[:self.top_k]
        for index, recommendation in enumerate(recommendations, 1):
            recommendation.rank = index

        await self.store_result("recommendations", recommendations)
        self.log_operation("recommendation_generation_complete", {
            "recommendations": len(recommendations), "mode": mode,
        })
        return recommendations, summary

    def _llm_generate(
        self,
        topic_map: TopicMap,
        claims: List[Claim],
        contradictions: List[Contradiction],
        research_gaps: List[ResearchGap],
        papers: List[PaperMetadata],
    ) -> Optional[Tuple[List[Recommendation], str]]:
        ranked_gaps = sorted(
            research_gaps, key=lambda gap: gap.priority, reverse=True
        )[:self.top_k]
        ranked_papers = sorted(
            papers, key=lambda paper: paper.relevance_score, reverse=True
        )[:self.top_k]

        lines = [
            f"Topic: {topic_map.main_topic}",
            (f"Counts: {len(papers)} papers, {len(claims)} claims, "
             f"{len(contradictions)} contradictions, {len(research_gaps)} gaps"),
            "Research gaps:",
        ]
        lines.extend(
            f"- id={gap.id}; priority={gap.priority:.3f}; {gap.description}; "
            f"questions={gap.potential_questions[:3]}"
            for gap in ranked_gaps
        )
        lines.append("Unresolved contradictions:")
        lines.extend(
            f"- id={item.id}; {item.explanation}" for item in contradictions[:5]
        )
        lines.append("Top papers:")
        lines.extend(
            f"- id={paper.id}; title={paper.title}; year={paper.year}"
            for paper in ranked_papers
        )

        prompt = (
            "You are a research planning assistant. Based only on the corpus context "
            "below, produce an executive summary and a ranked set of practical next "
            "actions. Do not invent paper ids, gap ids, findings, or numeric results. "
            "Use only ids present in the context. Return ONLY one JSON object with "
            "this shape: {\"executive_summary\": str, \"recommendations\": "
            "[{\"category\": one of next_step|reading|experiment|method_adoption|risk, "
            "\"title\": str, \"rationale\": str, \"action\": str, "
            "\"supporting_evidence\": [str], \"linked_gap_ids\": [str], "
            "\"linked_paper_ids\": [str], \"importance\": 0.0-1.0, "
            "\"tractability\": 0.0-1.0}]}.\n\nCorpus context:\n"
            + "\n".join(lines)
        )

        raw = llm_client.chat(
            prompt,
            max_tokens=2000,
            temperature=0.0,
            tracker=self.tracker,
            purpose="recommendations",
        ).strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            if self.tracker is not None:
                self.tracker.record_parse_failure("recommendations")
            self.logger.warning(f"Recommendation JSON parse failed: {exc}")
            return None

        try:
            summary = str(payload["executive_summary"]).strip()
            items = [_RecItem(**item) for item in payload["recommendations"]]
        except (KeyError, TypeError, ValueError) as exc:
            if self.tracker is not None:
                self.tracker.record_parse_failure("recommendations")
            self.logger.warning(f"Recommendation payload validation failed: {exc}")
            return None

        valid_gap_ids = {gap.id for gap in research_gaps}
        valid_paper_ids = {paper.id for paper in papers if paper.id}
        recommendations = []
        for index, item in enumerate(items):
            category = (
                item.category if item.category in RECOMMENDATION_CATEGORIES
                else "next_step"
            )
            priority = round(0.6 * item.importance + 0.4 * item.tractability, 3)
            recommendations.append(Recommendation(
                id=f"rec_llm_{index + 1}",
                category=category,
                title=item.title,
                rationale=item.rationale,
                action=item.action,
                supporting_evidence=item.supporting_evidence[:5],
                linked_gap_ids=[gid for gid in item.linked_gap_ids if gid in valid_gap_ids],
                linked_paper_ids=[pid for pid in item.linked_paper_ids if pid in valid_paper_ids],
                priority=priority,
                detection_method="llm",
            ))
        if not recommendations or not summary:
            return None
        return recommendations, summary

    def _rule_based_generate(
        self,
        topic_map: TopicMap,
        claims: List[Claim],
        contradictions: List[Contradiction],
        research_gaps: List[ResearchGap],
        papers: List[PaperMetadata],
    ) -> Tuple[List[Recommendation], str]:
        if not claims and not contradictions and not research_gaps:
            summary = (
                f"The corpus for {topic_map.main_topic} produced no extractable claims, "
                "contradictions, or research gaps, so evidence is currently insufficient "
                "for specific conclusions."
            )
            return [Recommendation(
                id="rec_expand_corpus",
                category="next_step",
                title="Expand the evidence corpus",
                rationale="No actionable findings were extracted from the current corpus.",
                action=("Broaden the search terms and sources, then rerun with lower claim "
                        "extraction thresholds and review the newly retrieved abstracts."),
                supporting_evidence=[
                    "0 claims, 0 contradictions, and 0 research gaps were available."
                ],
                priority=1.0,
                detection_method="rules",
            )], summary

        recommendations: List[Recommendation] = []
        valid_paper_ids = {paper.id for paper in papers if paper.id}
        for index, paper in enumerate(sorted(
            papers, key=lambda item: item.relevance_score, reverse=True
        )[:3], 1):
            relevance = max(0.0, min(1.0, paper.relevance_score))
            recommendations.append(Recommendation(
                id=f"rec_reading_{paper.id or index}",
                category="reading",
                title=f"Read: {paper.title}",
                rationale=(f"This is a high-relevance source for {topic_map.main_topic} "
                           f"({paper.year}, {paper.venue})."),
                action="Review its methods, evidence, and limitations before planning new work.",
                supporting_evidence=[f"Corpus relevance score: {relevance:.2f}"],
                linked_paper_ids=[paper.id] if paper.id else [],
                priority=round(0.6 * relevance + 0.4 * 0.9, 3),
                detection_method="rules",
            ))

        for index, gap in enumerate(sorted(
            research_gaps, key=lambda item: item.priority, reverse=True
        ), 1):
            importance = max(0.0, min(1.0, gap.score_components.get(
                "importance", gap.priority
            )))
            tractability = max(0.0, min(1.0, gap.score_components.get(
                "tractability", 0.65
            )))
            question = gap.potential_questions[0] if gap.potential_questions else gap.description
            category = "experiment" if gap.gap_type in (
                "methodological", "dataset", "evaluation", "contradiction_driven"
            ) else "next_step"
            recommendations.append(Recommendation(
                id=f"rec_gap_{gap.id or index}",
                category=category,
                title=f"Address gap: {gap.description}",
                rationale=(gap.evidence[0] if gap.evidence else
                           "The gap was ranked as important in the corpus analysis."),
                action=f"Design a focused study around: {question}",
                supporting_evidence=gap.evidence[:5],
                linked_gap_ids=[gap.id] if gap.id else [],
                priority=round(0.6 * importance + 0.4 * tractability, 3),
                detection_method="rules",
            ))

        for index, contradiction in enumerate(contradictions, 1):
            importance = max(0.0, min(1.0, contradiction.severity))
            recommendations.append(Recommendation(
                id=f"rec_risk_{contradiction.id or index}",
                category="risk",
                title="Resolve a conflicting finding",
                rationale=contradiction.explanation,
                action=("Compare study conditions, datasets, and methods, then reproduce the "
                        "conflicting result under a shared protocol."),
                supporting_evidence=[value for value in (
                    contradiction.evidence_claim1, contradiction.evidence_claim2
                ) if value],
                linked_paper_ids=[pid for pid in (
                    contradiction.paper1_id, contradiction.paper2_id
                ) if pid in valid_paper_ids],
                priority=round(0.6 * importance + 0.4 * 0.55, 3),
                detection_method="rules",
            ))

        summary = (
            f"The analysis of {len(papers)} papers produced {len(claims)} claims, "
            f"{len(contradictions)} contradictions, and {len(research_gaps)} research "
            f"gaps for {topic_map.main_topic}. Prioritize the highest-ranked actions "
            "below and validate them against the linked evidence."
        )
        return recommendations, summary
