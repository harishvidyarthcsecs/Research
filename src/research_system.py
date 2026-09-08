"""
Main Autonomous Research Agent System orchestrator.
"""
import logging
from typing import Callable, Dict, Any, List, Optional
from datetime import datetime

from .models.data_models import ResearchResults, TopicMap, PaperMetadata, Claim
from .agents import llm_client
from .agents.topic_expansion_agent import TopicExpansionAgent
from .agents.enhanced_paper_discovery_agent import EnhancedPaperDiscoveryAgent as PaperDiscoveryAgent
from .agents.claim_extraction_agent import ClaimExtractionAgent
from .agents.claim_normalization_agent import ClaimNormalizationAgent
from .agents.contradiction_detection_agent import ContradictionDetectionAgent
from .agents.research_gap_detection_agent import ResearchGapDetectionAgent
from .agents.citation_builder_agent import CitationBuilderAgent
from .agents.recommendation_agent import RecommendationAgent
from .memory.memory_store import MemoryStore


class AutonomousResearchSystem:
    """
    Main orchestrator for the autonomous research system.
    Coordinates all agents to perform end-to-end research.
    """
    
    def __init__(self, storage_path: str = "data/memory"):
        self.memory_store = MemoryStore(storage_path)
        self.logger = self._setup_logging()
        
        # Initialize agents
        self.topic_expansion_agent = TopicExpansionAgent(self.memory_store)
        self.paper_discovery_agent = PaperDiscoveryAgent(self.memory_store)
        self.claim_extraction_agent = ClaimExtractionAgent(self.memory_store)
        self.claim_normalization_agent = ClaimNormalizationAgent(self.memory_store)
        self.contradiction_detection_agent = ContradictionDetectionAgent(self.memory_store)
        self.research_gap_detection_agent = ResearchGapDetectionAgent(self.memory_store)
        self.citation_builder_agent = CitationBuilderAgent(self.memory_store)
        self.recommendation_agent = RecommendationAgent(self.memory_store)
        
        self.logger.info("Autonomous Research System initialized")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('research_system.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger("AutonomousResearchSystem")
    
    async def research(self, topic: str,
                       papers: Optional[List[PaperMetadata]] = None,
                       progress: Optional[Callable[..., None]] = None) -> ResearchResults:
        """
        Perform autonomous research on a given topic.

        Args:
            topic: Research topic or question
            papers: Optional frozen paper corpus. When given, Stage 2 discovery
                is skipped — used by the evaluation harness so runs are
                reproducible against a fixed set of papers.
            progress: Optional callback invoked as
                `progress(stage, name, state, **detail)` before and after each
                stage. The web app passes the job's event emitter so the browser
                can stream progress; CLI and eval runs pass nothing. The
                callback may raise (e.g. `ResearchCancelled`) to abort the run.

        Returns:
            ResearchResults: Comprehensive research findings
        """
        self.logger.info(f"Starting autonomous research on topic: {topic}")
        start_time = datetime.now()
        frozen_corpus = papers is not None

        def report(stage: int, name: str, state: str, **detail) -> None:
            """Forward a stage event, if anyone is listening."""
            if progress is not None:
                progress(stage, name, state, **detail)

        # Per-run LLM usage/cost tracking, shared by all agents
        tracker = llm_client.UsageTracker()
        for agent in (self.topic_expansion_agent,
                      self.claim_extraction_agent,
                      self.contradiction_detection_agent,
                      self.research_gap_detection_agent,
                      self.recommendation_agent):
            agent.tracker = tracker

        try:
            # Stage 1: Topic Expansion
            self.logger.info("Stage 1: Topic Expansion")
            report(1, "Topic Expansion", "running")
            topic_map = await self.topic_expansion_agent.process(topic)
            report(1, "Topic Expansion", "done",
                   subtopics=len(topic_map.subtopics),
                   keywords=len(topic_map.keywords))

            # Stage 2: Paper Discovery (skipped when a frozen corpus is supplied)
            if papers is None:
                self.logger.info("Stage 2: Paper Discovery")
                report(2, "Paper Discovery", "running")
                async with self.paper_discovery_agent:
                    papers = await self.paper_discovery_agent.process(topic_map)
                report(2, "Paper Discovery", "done", papers=len(papers))
            else:
                self.logger.info(f"Stage 2: Using frozen corpus of {len(papers)} papers")
                report(2, "Paper Discovery", "done", papers=len(papers), frozen=True)

            # Stage 3: Claim Extraction
            self.logger.info("Stage 3: Claim Extraction")
            report(3, "Claim Extraction", "running", papers=len(papers))
            claims = await self.claim_extraction_agent.process(papers)
            report(3, "Claim Extraction", "done", claims=len(claims),
                   **self._usage_detail(tracker))

            # Stage 4: Claim Normalization & Verification
            self.logger.info("Stage 4: Claim Normalization & Verification")
            report(4, "Claim Normalization", "running", claims=len(claims))
            normalized_claims = await self.claim_normalization_agent.process(claims)
            report(4, "Claim Normalization", "done", claims=len(normalized_claims))

            # Stage 5: Contradiction Detection
            self.logger.info("Stage 5: Contradiction Detection")
            report(5, "Contradiction Detection", "running", claims=len(normalized_claims))
            contradictions = await self.contradiction_detection_agent.process(
                normalized_claims, papers=papers)
            report(5, "Contradiction Detection", "done",
                   contradictions=len(contradictions), **self._usage_detail(tracker))

            # Stage 6: Research Gap Detection
            self.logger.info("Stage 6: Research Gap Detection")
            report(6, "Research Gap Detection", "running")
            research_gaps = await self.research_gap_detection_agent.process(
                topic_map, normalized_claims,
                contradictions=contradictions, papers=papers)
            report(6, "Research Gap Detection", "done", gaps=len(research_gaps),
                   **self._usage_detail(tracker))

            # Stage 7: Citation Building
            self.logger.info("Stage 7: Citation Building")
            report(7, "Citation Building", "running", papers=len(papers))
            citations = await self.citation_builder_agent.process(papers)
            report(7, "Citation Building", "done", citations=len(citations))

            # Stage 8: Recommendations
            self.logger.info("Stage 8: Recommendations")
            report(8, "Recommendations", "running")
            recommendations, executive_summary = await self.recommendation_agent.process(
                topic_map, normalized_claims, contradictions, research_gaps, papers)
            report(8, "Recommendations", "done",
                   recommendations=len(recommendations), **self._usage_detail(tracker))

            # Stage 9: Store in Long-term Memory
            self.logger.info("Stage 9: Storing in Long-term Memory")
            report(9, "Storing in Memory", "running")
            await self._store_in_memory(
                topic_map, papers, normalized_claims, contradictions, research_gaps,
                recommendations, executive_summary)
            report(9, "Storing in Memory", "done")

            duration = datetime.now() - start_time

            # Compile results
            info = llm_client.provider_info()
            results = ResearchResults(
                topic_map=topic_map,
                papers=papers,
                claims=normalized_claims,
                contradictions=contradictions,
                research_gaps=research_gaps,
                citations=citations,
                recommendations=recommendations,
                executive_summary=executive_summary,
                total_papers_analyzed=len(papers),
                total_claims_extracted=len(normalized_claims),
                usage=tracker.summary(),
                run_metadata={
                    "provider": info.get("provider"),
                    "model": info.get("model"),
                    "temperature": 0.0,
                    "duration_s": round(duration.total_seconds(), 2),
                    "frozen_corpus": frozen_corpus,
                },
            )

            self.logger.info(f"Research completed in {duration.total_seconds():.2f} seconds")

            return results
            
        except Exception as e:
            self.logger.error(f"Error during research: {e}")
            raise

    @staticmethod
    def _usage_detail(tracker) -> Dict[str, Any]:
        """Running LLM cost/token totals, safe to call after any stage."""
        try:
            summary = tracker.summary()
            return {
                "calls": summary.get("calls", 0),
                "cost_usd": summary.get("estimated_cost_usd", 0.0),
            }
        except Exception:
            return {}

    async def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory store statistics."""
        return await self.memory_store.get_cache_stats()
    
    async def _store_in_memory(self, topic_map: TopicMap, papers: List[PaperMetadata], 
                             claims: List[Claim], contradictions: List[Any], 
                             research_gaps: List[Any], recommendations: List[Any],
                             executive_summary: str) -> None:
        """Store research results in long-term memory."""
        
        # Store topic map
        await self.memory_store.store("latest_topic_map", topic_map)
        
        # Store papers
        await self.memory_store.store("latest_papers", papers)
        
        # Store claims
        await self.memory_store.store("latest_claims", claims)
        
        # Store contradictions
        await self.memory_store.store("latest_contradictions", contradictions)
        
        # Store research gaps
        await self.memory_store.store("latest_research_gaps", research_gaps)

        # Store the actionable synthesis layer
        await self.memory_store.store("latest_recommendations", recommendations)
        await self.memory_store.store("latest_executive_summary", executive_summary)
        
        self.logger.info("Research results stored in long-term memory")
