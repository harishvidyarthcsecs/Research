"""
Agents package for the Autonomous Research Agent System.
"""

from .base_agent import BaseAgent
from .topic_expansion_agent import TopicExpansionAgent
# The legacy paper_discovery_agent (simulated Semantic Scholar) is deprecated;
# PaperDiscoveryAgent now refers to the real multi-source enhanced agent.
from .enhanced_paper_discovery_agent import EnhancedPaperDiscoveryAgent
from .enhanced_paper_discovery_agent import EnhancedPaperDiscoveryAgent as PaperDiscoveryAgent
from .claim_extraction_agent import ClaimExtractionAgent
from .claim_normalization_agent import ClaimNormalizationAgent
from .contradiction_detection_agent import ContradictionDetectionAgent
from .research_gap_detection_agent import ResearchGapDetectionAgent
from .citation_builder_agent import CitationBuilderAgent

__all__ = [
    "BaseAgent",
    "TopicExpansionAgent",
    "PaperDiscoveryAgent",
    "EnhancedPaperDiscoveryAgent",
    "ClaimExtractionAgent",
    "ClaimNormalizationAgent",
    "ContradictionDetectionAgent",
    "ResearchGapDetectionAgent",
    "CitationBuilderAgent"
]