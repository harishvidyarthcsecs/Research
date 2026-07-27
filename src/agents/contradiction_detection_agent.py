"""
Contradiction Detection Agent.

Primary mode ("llm"): ContraCrow-style two-stage detection — retrieve the
top-K most similar cross-paper claim pairs, then have an LLM judge each pair
on an 11-point Likert scale (1 = strong support, 6 = neutral/unrelated,
11 = strong contradiction) with verbatim evidence sentences.

Fallback mode ("pattern"): the original pattern-matching detector, kept both
as the no-API-key fallback and as the rule-based ablation baseline for
evaluation runs (set CONTRADICTION_MODE=pattern).
"""
import asyncio
import json
import os
import re
from typing import List, Dict, Any, Optional, Tuple
from itertools import combinations

from pydantic import BaseModel, Field

from ..models.data_models import Claim, Contradiction, PaperMetadata
from .base_agent import BaseAgent
from . import llm_client
from .candidate_pair_retriever import retrieve_candidate_pairs


class _PairJudgment(BaseModel):
    """Validated shape of one LLM pair judgment."""
    pair: int
    likert: int = Field(ge=1, le=11)
    verdict: str = "neutral"
    contradiction_type: str = "direct"
    explanation: str = ""
    evidence_1: str = ""
    evidence_2: str = ""


class ContradictionDetectionAgent(BaseAgent):
    """Agent responsible for detecting contradictions between claims."""

    def __init__(self, memory_store=None, similarity_threshold: float = 0.7,
                 mode: Optional[str] = None, likert_threshold: int = 8,
                 top_k_pairs: int = 40, batch_size: int = 5):
        super().__init__("ContradictionDetectionAgent", memory_store)
        self.similarity_threshold = similarity_threshold
        self.mode = mode  # None = auto: "llm" if a provider is available
        self.likert_threshold = likert_threshold
        self.top_k_pairs = top_k_pairs
        self.batch_size = batch_size
        self.tracker: Optional[llm_client.UsageTracker] = None
        self.contradiction_patterns = self._initialize_contradiction_patterns()

    def _resolve_mode(self) -> str:
        mode = self.mode or os.getenv("CONTRADICTION_MODE")
        if mode in ("llm", "pattern"):
            return mode
        return "llm" if llm_client.get_provider() is not None else "pattern"

    async def process(self, claims: List[Claim],
                      papers: Optional[List[PaperMetadata]] = None) -> List[Contradiction]:
        """
        Detect contradictions between claims.

        Args:
            claims: List of claims to analyze
            papers: Optional paper metadata used to give the LLM judge
                title/year context for each claim's source paper

        Returns:
            List of detected contradictions
        """
        mode = self._resolve_mode()
        self.log_operation("contradiction_detection_start", {
            "claim_count": len(claims),
            "mode": mode,
        })

        if mode == "llm":
            try:
                contradictions = await self._llm_detect(claims, papers or [])
            except Exception as e:  # no provider available, or the call itself failed
                self.logger.warning(f"LLM judge unavailable ({e}); falling back to patterns")
                mode = "pattern"
                contradictions = self._pattern_detect(claims)
        else:
            contradictions = self._pattern_detect(claims)

        await self.store_result("detected_contradictions", contradictions)

        self.log_operation("contradiction_detection_complete", {
            "contradictions_found": len(contradictions),
            "mode": mode,
        })

        return contradictions

    # ------------------------------------------------------------------ #
    # LLM judge (primary)                                                #
    # ------------------------------------------------------------------ #

    _LIKERT_PROMPT_HEADER = (
        "You are judging pairs of scientific claims extracted from different "
        "papers. For each pair, rate the relationship on an 11-point Likert "
        "scale:\n"
        "  1 = the claims strongly SUPPORT each other\n"
        "  6 = the claims are UNRELATED or neutral\n"
        "  11 = the claims strongly CONTRADICT each other\n"
        "A contradiction means the claims cannot both be true as stated "
        "(opposite findings, incompatible results on the same task/dataset, "
        "or conflicting conclusions under the same conditions). Different "
        "numbers on different datasets/settings are NOT automatically a "
        "contradiction.\n\n"
        "Return ONLY a JSON array with one object per pair, keys:\n"
        "  pair (int), likert (int 1-11), "
        "verdict (\"support\"|\"neutral\"|\"contradiction\"), "
        "contradiction_type (\"direct\"|\"conditional\"|\"methodological\"), "
        "explanation (one sentence), "
        "evidence_1 (verbatim quote from Claim A), "
        "evidence_2 (verbatim quote from Claim B).\n\n"
    )

    async def _llm_detect(self, claims: List[Claim],
                          papers: List[PaperMetadata]) -> List[Contradiction]:
        pairs = retrieve_candidate_pairs(claims, top_k=self.top_k_pairs)
        if not pairs:
            return []

        paper_lookup = self._build_paper_lookup(papers)

        batches = [pairs[i:i + self.batch_size]
                   for i in range(0, len(pairs), self.batch_size)]

        semaphore = asyncio.Semaphore(3)
        loop = asyncio.get_event_loop()

        async def judge(batch):
            async with semaphore:
                return await loop.run_in_executor(
                    None, self._judge_batch, batch, paper_lookup)

        results = await asyncio.gather(*[judge(b) for b in batches],
                                       return_exceptions=True)

        contradictions: List[Contradiction] = []
        for result in results:
            if isinstance(result, Exception):
                if isinstance(result, RuntimeError):
                    raise result
                self.logger.warning(f"Judge batch failed: {result}")
                continue
            contradictions.extend(result)
        return contradictions

    @staticmethod
    def _build_paper_lookup(papers: List[PaperMetadata]) -> Dict[str, str]:
        """Map heuristic paper ids to 'Title (year)' context strings."""
        lookup: Dict[str, str] = {}
        for paper in papers:
            label = f"{paper.title} ({paper.year})"
            if paper.doi:
                lookup[paper.doi.replace("/", "_").replace(".", "_")] = label
            if paper.arxiv_id:
                lookup[f"arxiv_{paper.arxiv_id}"] = label
            words = re.findall(r"\w+", paper.title.lower())[:5]
            lookup[f"{'_'.join(words)}_{paper.year}"] = label
        return lookup

    def _format_pair(self, index: int, c1: Claim, c2: Claim,
                     paper_lookup: Dict[str, str]) -> str:
        def describe(label: str, claim: Claim) -> str:
            paper = paper_lookup.get(claim.paper_id, claim.paper_id)
            extras = []
            if claim.metrics:
                extras.append(f"metrics: {claim.metrics}")
            if claim.datasets:
                extras.append(f"datasets: {', '.join(claim.datasets)}")
            if claim.conditions:
                extras.append(f"conditions: {', '.join(claim.conditions[:3])}")
            extra_str = f" [{'; '.join(extras)}]" if extras else ""
            return f"  Claim {label} (paper: {paper}): \"{claim.statement}\"{extra_str}"

        return (f"Pair {index}:\n"
                f"{describe('A', c1)}\n"
                f"{describe('B', c2)}")

    def _judge_batch(self, batch: List[Tuple[Claim, Claim, float]],
                     paper_lookup: Dict[str, str]) -> List[Contradiction]:
        prompt = self._LIKERT_PROMPT_HEADER + "\n\n".join(
            self._format_pair(i + 1, c1, c2, paper_lookup)
            for i, (c1, c2, _score) in enumerate(batch)
        )

        parsed = self._call_and_parse(prompt, expected=len(batch))
        if parsed is None:
            # Batched call unparseable twice: degrade to per-pair calls
            judgments = []
            for i, (c1, c2, _score) in enumerate(batch):
                single_prompt = self._LIKERT_PROMPT_HEADER + self._format_pair(
                    1, c1, c2, paper_lookup)
                single = self._call_and_parse(single_prompt, expected=1)
                if single:
                    judgments.append((i, single[0]))
        else:
            judgments = [(j.pair - 1, j) for j in parsed]

        contradictions = []
        for pair_index, judgment in judgments:
            if not (0 <= pair_index < len(batch)):
                continue
            if judgment.likert < self.likert_threshold:
                continue
            c1, c2, _score = batch[pair_index]
            contradictions.append(Contradiction(
                claim1_id=c1.id,
                claim2_id=c2.id,
                contradiction_type=judgment.contradiction_type
                if judgment.contradiction_type in ("direct", "conditional", "methodological")
                else "direct",
                explanation=judgment.explanation or "LLM judged these claims contradictory",
                severity=max(0.0, min(1.0, (judgment.likert - 6) / 5)),
                likert_score=judgment.likert,
                verdict=judgment.verdict or "contradiction",
                evidence_claim1=judgment.evidence_1 or None,
                evidence_claim2=judgment.evidence_2 or None,
                paper1_id=c1.paper_id,
                paper2_id=c2.paper_id,
                detection_method="llm_judge",
            ))
        return contradictions

    def _call_and_parse(self, prompt: str,
                        expected: int) -> Optional[List[_PairJudgment]]:
        """Call the LLM and parse/validate its JSON, retrying once."""
        for attempt in range(2):
            raw = llm_client.chat(
                prompt,
                max_tokens=2048,
                temperature=0.0,
                tracker=self.tracker,
                purpose="contradiction_judge",
            ).strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            try:
                items = json.loads(raw)
                if isinstance(items, dict):
                    items = [items]
                return [_PairJudgment(**item) for item in items][:expected]
            except Exception as e:
                if self.tracker is not None:
                    self.tracker.record_parse_failure("contradiction_judge")
                self.logger.warning(
                    f"Judge JSON parse failed (attempt {attempt + 1}): {e}")
        return None

    # ------------------------------------------------------------------ #
    # Pattern-based detection (fallback + ablation baseline)             #
    # ------------------------------------------------------------------ #

    def _initialize_contradiction_patterns(self) -> Dict[str, Any]:
        """Initialize patterns for detecting contradictions."""
        return {
            "direct_opposites": [
                ("increases", "decreases"),
                ("improves", "worsens"),
                ("higher", "lower"),
                ("better", "worse"),
                ("outperforms", "underperforms"),
                ("superior", "inferior"),
                ("effective", "ineffective")
            ],
            "quantitative_thresholds": {
                "accuracy": 0.1,  # 10% difference threshold
                "precision": 0.1,
                "recall": 0.1,
                "f1_score": 0.1,
                "auc": 0.05,
                "rmse": 0.2,
                "mae": 0.2
            },
        }

    def _pattern_detect(self, claims: List[Claim]) -> List[Contradiction]:
        contradictions = []
        for claim1, claim2 in combinations(claims, 2):
            contradiction = self._detect_contradiction(claim1, claim2)
            if contradiction:
                contradictions.append(contradiction)
        return contradictions

    def _detect_contradiction(self, claim1: Claim, claim2: Claim) -> Optional[Contradiction]:
        """Detect contradiction between two claims via patterns."""

        # Skip if claims are from the same paper (less likely to contradict)
        if claim1.paper_id == claim2.paper_id:
            return None

        for check in (self._check_direct_contradiction,
                      self._check_metric_contradiction,
                      self._check_conditional_contradiction):
            contradiction = check(claim1, claim2)
            if contradiction:
                contradiction.paper1_id = claim1.paper_id
                contradiction.paper2_id = claim2.paper_id
                contradiction.detection_method = "pattern"
                return contradiction

        return None

    def _check_direct_contradiction(self, claim1: Claim, claim2: Claim) -> Optional[Contradiction]:
        """Check for direct textual contradictions."""

        # Check if claims are about similar topics
        if not self._are_claims_related(claim1, claim2):
            return None

        statement1_lower = claim1.statement.lower()
        statement2_lower = claim2.statement.lower()

        # Check for opposite terms
        for positive, negative in self.contradiction_patterns["direct_opposites"]:
            if (positive in statement1_lower and negative in statement2_lower) or \
               (negative in statement1_lower and positive in statement2_lower):

                severity = self._calculate_contradiction_severity(claim1, claim2, "direct")

                return Contradiction(
                    claim1_id=claim1.id,
                    claim2_id=claim2.id,
                    contradiction_type="direct",
                    explanation=f"Claims contain opposite terms: '{positive}' vs '{negative}'",
                    severity=severity
                )

        return None

    def _check_metric_contradiction(self, claim1: Claim, claim2: Claim) -> Optional[Contradiction]:
        """Check for contradictions in reported metrics."""

        if not claim1.metrics or not claim2.metrics:
            return None

        # Find common metrics
        common_metrics = set(claim1.metrics.keys()) & set(claim2.metrics.keys())

        for metric in common_metrics:
            value1 = claim1.metrics[metric]
            value2 = claim2.metrics[metric]

            if isinstance(value1, (int, float)) and isinstance(value2, (int, float)):
                threshold = self.contradiction_patterns["quantitative_thresholds"].get(metric, 0.15)

                if abs(value1 - value2) > threshold:
                    # Check if they're testing on similar conditions
                    if self._have_similar_conditions(claim1, claim2):
                        severity = self._calculate_contradiction_severity(claim1, claim2, "metric")

                        return Contradiction(
                            claim1_id=claim1.id,
                            claim2_id=claim2.id,
                            contradiction_type="methodological",
                            explanation=f"Significant difference in {metric}: {value1:.3f} vs {value2:.3f}",
                            severity=severity
                        )

        return None

    def _check_conditional_contradiction(self, claim1: Claim, claim2: Claim) -> Optional[Contradiction]:
        """Check for contradictions under specific conditions."""

        # Check if claims have overlapping datasets
        common_datasets = set(claim1.datasets) & set(claim2.datasets)

        if common_datasets:
            # Look for contradictory statements about the same dataset
            for dataset in common_datasets:
                if self._statements_contradict_on_dataset(claim1, claim2, dataset):
                    severity = self._calculate_contradiction_severity(claim1, claim2, "conditional")

                    return Contradiction(
                        claim1_id=claim1.id,
                        claim2_id=claim2.id,
                        contradiction_type="conditional",
                        explanation=f"Contradictory results on dataset {dataset}",
                        severity=severity
                    )

        return None

    def _are_claims_related(self, claim1: Claim, claim2: Claim) -> bool:
        """Check if two claims are related enough to potentially contradict."""

        # Check for common keywords
        words1 = set(re.findall(r'\b\w+\b', claim1.statement.lower()))
        words2 = set(re.findall(r'\b\w+\b', claim2.statement.lower()))

        common_words = words1 & words2

        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        meaningful_common = common_words - stop_words

        # Claims are related if they share enough meaningful words
        return len(meaningful_common) >= 2

    def _have_similar_conditions(self, claim1: Claim, claim2: Claim) -> bool:
        """Check if claims were tested under similar conditions."""

        # Check for common datasets
        if set(claim1.datasets) & set(claim2.datasets):
            return True

        # Check for similar experimental conditions
        conditions1 = [c.lower() for c in claim1.conditions]
        conditions2 = [c.lower() for c in claim2.conditions]

        for c1 in conditions1:
            for c2 in conditions2:
                if self._conditions_similar(c1, c2):
                    return True

        return False

    def _conditions_similar(self, condition1: str, condition2: str) -> bool:
        """Check if two conditions are similar."""

        # Simple similarity check based on common words
        words1 = set(re.findall(r'\b\w+\b', condition1.lower()))
        words2 = set(re.findall(r'\b\w+\b', condition2.lower()))

        if not words1 or not words2:
            return False

        intersection = words1 & words2
        union = words1 | words2

        # Jaccard similarity
        similarity = len(intersection) / len(union) if union else 0

        return similarity > 0.3

    def _statements_contradict_on_dataset(self, claim1: Claim, claim2: Claim, dataset: str) -> bool:
        """Check if statements contradict each other regarding a specific dataset."""

        statement1 = claim1.statement.lower()
        statement2 = claim2.statement.lower()
        dataset_lower = dataset.lower()

        # Both statements should mention the dataset
        if dataset_lower not in statement1 or dataset_lower not in statement2:
            return False

        # Look for contradictory terms in the context of the dataset
        for positive, negative in self.contradiction_patterns["direct_opposites"]:
            if (positive in statement1 and negative in statement2) or \
               (negative in statement1 and positive in statement2):
                return True

        return False

    def _calculate_contradiction_severity(self, claim1: Claim, claim2: Claim,
                                        contradiction_type: str) -> float:
        """Calculate the severity of a contradiction."""

        base_severity = {
            "direct": 0.8,
            "methodological": 0.6,
            "conditional": 0.4
        }.get(contradiction_type, 0.5)

        # Adjust based on claim confidence
        confidence_factor = (claim1.confidence + claim2.confidence) / 2

        severity = base_severity * confidence_factor

        return min(severity, 1.0)

    def get_contradiction_summary(self, contradictions: List[Contradiction]) -> Dict[str, Any]:
        """Get summary statistics about detected contradictions."""

        if not contradictions:
            return {"total": 0}

        by_type = {}
        severities = []

        for contradiction in contradictions:
            # Count by type
            if contradiction.contradiction_type not in by_type:
                by_type[contradiction.contradiction_type] = 0
            by_type[contradiction.contradiction_type] += 1

            severities.append(contradiction.severity)

        return {
            "total": len(contradictions),
            "by_type": by_type,
            "avg_severity": sum(severities) / len(severities),
            "high_severity": len([s for s in severities if s > 0.7]),
            "medium_severity": len([s for s in severities if 0.4 <= s <= 0.7]),
            "low_severity": len([s for s in severities if s < 0.4])
        }
