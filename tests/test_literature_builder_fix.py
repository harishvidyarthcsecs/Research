#!/usr/bin/env python3
"""
Test script for the enhanced literature builder with abstract processing and accurate bibliographic data.
"""

import sys
import os
import asyncio
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import directly without going through __init__.py
from models.data_models import (
    PaperMetadata, Claim, ResearchResults, TopicMap, 
    Contradiction, ResearchGap, Citation
)

# Import the literature builder directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'agents'))
from literature_builder_agent import LiteratureBuilderAgent

def create_test_data():
    """Create test data with real-looking papers and abstracts."""
    
    # Create sample papers with realistic abstracts and proper IDs
    papers = [
        PaperMetadata(
            title="Deep learning approaches for climate change prediction",
            authors=["Y. Saad", "M.H. Schultz"],
            year=2023,
            venue="Nature Climate Change",
            doi="10.1038/s41558-023-01234-5",
            abstract="Climate change prediction remains one of the most challenging problems in environmental science. This study presents a novel deep learning framework that combines convolutional neural networks with long short-term memory networks to predict regional climate patterns. The proposed method achieves 95% accuracy on temperature predictions and 87% accuracy on precipitation forecasting. Our results demonstrate significant improvements over traditional statistical methods and provide new insights into climate modeling approaches.",
            relevance_score=0.95
        ),
        PaperMetadata(
            title="Machine learning for weather forecasting: A comprehensive review",
            authors=["K. Patel", "R. Johnson", "S. Chen"],
            year=2022,
            venue="Journal of Climate",
            doi="10.1175/JCLI-D-22-0123.1",
            abstract="Weather forecasting has evolved significantly with the integration of machine learning techniques. This comprehensive review examines the application of various ML algorithms including random forests, support vector machines, and neural networks in meteorological predictions. We analyze 150 studies published between 2015-2022 and identify key trends in accuracy improvements. The review highlights that ensemble methods show the most promise for operational weather forecasting systems.",
            relevance_score=0.88
        ),
        PaperMetadata(
            title="Ensemble methods for climate model uncertainty quantification",
            authors=["A. Thompson", "B. Williams"],
            year=2024,
            venue="Geophysical Research Letters",
            doi="10.1029/2024GL123456",
            abstract="Uncertainty quantification in climate models is crucial for reliable predictions and policy decisions. This paper introduces a Bayesian ensemble approach that combines multiple climate models to reduce prediction uncertainty. The method incorporates model weights based on historical performance and provides confidence intervals for temperature and precipitation projections. Results show 30% reduction in prediction uncertainty compared to single-model approaches.",
            relevance_score=0.92
        )
    ]
    
    # Add proper IDs to papers
    for i, paper in enumerate(papers):
        paper.id = f"paper_{i+1}"
    
    # Create sample claims with matching paper IDs
    claims = [
        Claim(
            id="claim_1",
            statement="Deep learning models achieve 95% accuracy in temperature prediction tasks",
            paper_id="paper_1",  # Match first paper
            confidence=0.95,
            metrics={"accuracy": 0.95, "rmse": 0.12},
            datasets=["ERA5", "NCEP"]
        ),
        Claim(
            id="claim_2", 
            statement="Ensemble methods outperform single models in weather forecasting",
            paper_id="paper_2",  # Match second paper
            confidence=0.88,
            metrics={"accuracy": 0.88, "mae": 0.15},
            datasets=["GFS", "ECMWF"]
        ),
        Claim(
            id="claim_3",
            statement="Bayesian ensemble approaches reduce prediction uncertainty by 30%",
            paper_id="paper_3",  # Match third paper
            confidence=0.92,
            metrics={"uncertainty_reduction": 0.30},
            datasets=["CMIP6"]
        )
    ]
    
    # Create topic map
    topic_map = TopicMap(
        main_topic="Climate Change Prediction using Machine Learning",
        subtopics=["Deep Learning", "Weather Forecasting", "Uncertainty Quantification"],
        methods=["Neural Networks", "Ensemble Methods", "Bayesian Approaches"],
        keywords=["climate", "prediction", "machine learning", "deep learning"]
    )
    
    # Create research results
    research_results = ResearchResults(
        topic_map=topic_map,
        papers=papers,
        claims=claims,
        contradictions=[],
        research_gaps=[],
        citations=[],
        total_papers_analyzed=len(papers),
        total_claims_extracted=len(claims)
    )
    
    return research_results

async def test_literature_builder():
    """Test the literature builder with enhanced abstract processing."""
    
    print("🧪 Testing Enhanced Literature Builder")
    print("=" * 50)
    
    # Create test data
    research_results = create_test_data()
    
    # Initialize literature builder
    literature_agent = LiteratureBuilderAgent()
    
    try:
        # Generate literature
        print("📚 Generating literature from abstracts...")
        literature_document = await literature_agent.process(research_results)
        
        # Display results
        print(f"\n📖 Literature Generated Successfully!")
        print(f"Title: {literature_document.outline.title}")
        print(f"Sections: {len(literature_document.sections)}")
        print(f"Total Words: {literature_document.total_word_count}")
        print(f"Bibliography Entries: {len(literature_document.bibliography)}")
        
        # Show each section
        for i, section in enumerate(literature_document.sections, 1):
            print(f"\n--- Section {i}: {section.title} ---")
            print(f"Word Count: {section.word_count}")
            print(f"Content Preview: {section.content[:200]}...")
            if section.citations:
                print(f"Citations: {len(section.citations)} references")
        
        # Show bibliography samples
        print(f"\n--- Bibliography Sample ---")
        for i, entry in enumerate(literature_document.bibliography[:3], 1):
            print(f"{i}. {entry}")
        
        # Test CrossRef API integration
        print(f"\n🔍 Testing CrossRef API Integration...")
        sample_paper = research_results.papers[0]
        volume_info = literature_agent._extract_volume_info(sample_paper)
        print(f"Volume Info for {sample_paper.title[:50]}...")
        print(f"  Volume: {volume_info.get('volume', 'Not found')}")
        print(f"  Issue: {volume_info.get('issue', 'Not found')}")
        print(f"  Pages: {volume_info.get('pages', 'Not found')}")
        
        # Test bibitem key generation
        print(f"\n🔑 Testing Bibitem Key Generation...")
        for paper in research_results.papers:
            key = literature_agent._generate_bibitem_key(paper)
            print(f"  {paper.authors[0] if paper.authors else 'Unknown'} ({paper.year}) -> {key}")
        
        print(f"\n✅ All tests completed successfully!")
        
        return literature_document
        
    except Exception as e:
        print(f"\n❌ Error during literature generation: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # Run the test
    result = asyncio.run(test_literature_builder())
    
    if result:
        print(f"\n🎉 Literature Builder Test Successful!")
        print(f"Generated {result.total_word_count} words across {len(result.sections)} sections")
    else:
        print(f"\n💥 Literature Builder Test Failed!")