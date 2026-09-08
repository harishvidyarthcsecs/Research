"""
Tests for the Autonomous Research Agent System.
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock

from src.research_system import AutonomousResearchSystem
from src.models.data_models import TopicMap, PaperMetadata, Claim


class TestAutonomousResearchSystem:
    """Test cases for the main research system."""
    
    @pytest.fixture
    def research_system(self):
        """Create a research system instance for testing."""
        return AutonomousResearchSystem(storage_path="test_data/memory")
    
    @pytest.fixture
    def sample_topic_map(self):
        """Create a sample topic map for testing."""
        return TopicMap(
            main_topic="Graph Neural Networks in Drug Discovery",
            subtopics=["Molecular Property Prediction", "Drug-Target Interaction"],
            methods=["Graph Convolution", "Message Passing"],
            datasets=["ChEMBL", "PubChem"],
            keywords=["graph neural network", "drug discovery", "molecular"]
        )
    
    @pytest.fixture
    def sample_papers(self):
        """Create sample papers for testing."""
        return [
            PaperMetadata(
                title="Graph Neural Networks for Drug Discovery",
                authors=["John Doe", "Jane Smith"],
                year=2023,
                venue="Nature",
                abstract="This paper presents a novel approach using GNNs for drug discovery...",
                relevance_score=0.95
            ),
            PaperMetadata(
                title="Molecular Property Prediction with Graph Attention",
                authors=["Alice Johnson"],
                year=2022,
                venue="ICML",
                abstract="We propose a graph attention mechanism for molecular property prediction...",
                relevance_score=0.88
            )
        ]
    
    @pytest.mark.asyncio
    async def test_research_pipeline(self, research_system, sample_topic_map, sample_papers):
        """Test the complete research pipeline."""
        # Mock the agents
        research_system.topic_expansion_agent.process = AsyncMock(return_value=sample_topic_map)
        research_system.paper_discovery_agent.process = AsyncMock(return_value=sample_papers)
        research_system.claim_extraction_agent.process = AsyncMock(return_value=[])
        research_system.claim_normalization_agent.process = AsyncMock(return_value=[])
        research_system.contradiction_detection_agent.process = AsyncMock(return_value=[])
        research_system.research_gap_detection_agent.process = AsyncMock(return_value=[])
        research_system.citation_builder_agent.process = AsyncMock(return_value=[])
        research_system.recommendation_agent.process = AsyncMock(return_value=([], "Test summary"))
        
        # Run research
        results = await research_system.research("Graph Neural Networks in Drug Discovery")
        
        # Verify results
        assert results.topic_map == sample_topic_map
        assert len(results.papers) == 2
        assert results.total_papers_analyzed == 2
        assert results.generated_at is not None
    
    def test_bibtex_generation(self, research_system, sample_papers):
        """Test BibTeX citation generation."""
        paper = sample_papers[0]
        bibtex = research_system.citation_builder_agent._generate_bibtex(paper, paper.id)
        
        assert "Graph Neural Networks for Drug Discovery" in bibtex
        assert "John Doe and Jane Smith" in bibtex
        assert "2023" in bibtex
        assert "@article" in bibtex
    
    def test_apa_generation(self, research_system, sample_papers):
        """Test APA citation generation."""
        paper = sample_papers[0]
        apa = research_system.citation_builder_agent._generate_apa(paper)
        
        assert "Doe, J. & Smith, J." in apa
        assert "(2023)" in apa
        assert "Graph Neural Networks for Drug Discovery" in apa
    
    def test_ieee_generation(self, research_system, sample_papers):
        """Test IEEE citation generation."""
        paper = sample_papers[0]
        ieee = research_system.citation_builder_agent._generate_ieee(paper)
        
        assert "John Doe, Jane Smith" in ieee
        assert "Graph Neural Networks for Drug Discovery" in ieee
        assert "2023" in ieee


class TestTopicExpansionAgent:
    """Test cases for the Topic Expansion Agent."""
    
    @pytest.fixture
    def topic_expansion_agent(self):
        """Create a topic expansion agent for testing."""
        from src.agents.topic_expansion_agent import TopicExpansionAgent
        return TopicExpansionAgent(mode="rules")
    
    @pytest.mark.asyncio
    async def test_topic_expansion(self, topic_expansion_agent):
        """Test topic expansion functionality."""
        topic = "Graph Neural Networks in Drug Discovery"
        topic_map = await topic_expansion_agent.process(topic)
        
        assert topic_map.main_topic == topic
        assert len(topic_map.subtopics) > 0
        assert len(topic_map.keywords) > 0
        keywords = {kw.lower() for kw in topic_map.keywords}
        assert {"graph", "neural", "networks"} <= keywords
    
    def test_subtopic_extraction(self, topic_expansion_agent):
        """Test subtopic extraction."""
        topic = "Graph Neural Networks in Drug Discovery"
        subtopics = topic_expansion_agent._extract_subtopics(topic)
        
        assert len(subtopics) > 0
        assert any("Graph" in subtopic for subtopic in subtopics)
    
    def test_keyword_extraction(self, topic_expansion_agent):
        """Test keyword extraction."""
        topic = "Graph Neural Networks in Drug Discovery"
        keywords = topic_expansion_agent._extract_keywords(topic)
        
        assert len(keywords) > 0
        assert "graph" in keywords
        assert "neural" in keywords


class TestClaimExtractionAgent:
    """Test cases for the Claim Extraction Agent."""
    
    @pytest.fixture
    def claim_extraction_agent(self):
        """Create a claim extraction agent for testing."""
        from src.agents.claim_extraction_agent import ClaimExtractionAgent
        return ClaimExtractionAgent()
    
    def test_metric_extraction(self, claim_extraction_agent):
        """Test metric extraction from sentences."""
        sentence = "The model achieves an accuracy of 95.2% on the test dataset."
        metrics = claim_extraction_agent._extract_metrics(sentence)
        
        assert "accuracy" in metrics
        assert metrics["accuracy"] == 95.2
    
    def test_dataset_extraction(self, claim_extraction_agent):
        """Test dataset extraction from text."""
        text = "We evaluated our method on ChEMBL and PubChem datasets."
        datasets = claim_extraction_agent._extract_datasets(text)
        
        assert "ChEMBL" in datasets
        assert "PubChem" in datasets
    
    def test_sentence_splitting(self, claim_extraction_agent):
        """Test sentence splitting functionality."""
        paper = PaperMetadata(
            id="paper_1",
            title="Metric extraction",
            authors=["Test Author"],
            year=2024,
            venue="Test Journal",
            abstract="",
        )
        claims = claim_extraction_agent._regex_extract(
            "The model achieves accuracy of 95.2%. The approach is state-of-the-art!",
            paper.id,
            paper,
        )

        assert len(claims) == 2
        assert claims[0].metrics["accuracy"] == 95.2
        assert "state-of-the-art" in claims[1].statement


if __name__ == "__main__":
    pytest.main([__file__])
