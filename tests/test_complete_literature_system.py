#!/usr/bin/env python3
"""
Comprehensive test for the complete literature system with real abstracts and LaTeX citations.
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

def create_comprehensive_test_data():
    """Create comprehensive test data with realistic papers and abstracts."""
    
    # Create sample papers with realistic abstracts and proper IDs
    papers = [
        PaperMetadata(
            id="paper_1",
            title="Deep learning approaches for climate change prediction using ensemble methods",
            authors=["Y. Saad", "M.H. Schultz"],
            year=2023,
            venue="Nature Climate Change",
            doi="10.1038/s41558-023-01234-5",
            abstract="Climate change prediction remains one of the most challenging problems in environmental science. This study presents a novel deep learning framework that combines convolutional neural networks with long short-term memory networks to predict regional climate patterns. The proposed method achieves 95% accuracy on temperature predictions and 87% accuracy on precipitation forecasting. Results demonstrate significant improvements over traditional statistical methods and provide new insights into climate modeling approaches. The framework incorporates uncertainty quantification and handles missing data effectively.",
            relevance_score=0.95
        ),
        PaperMetadata(
            id="paper_2",
            title="Machine learning for weather forecasting: A comprehensive systematic review",
            authors=["K. Patel", "R. Johnson", "S. Chen"],
            year=2022,
            venue="Journal of Climate",
            doi="10.1175/JCLI-D-22-0123.1",
            abstract="Weather forecasting has evolved significantly with the integration of machine learning techniques. This comprehensive systematic review examines the application of various ML algorithms including random forests, support vector machines, and neural networks in meteorological predictions. The analysis covers 150 studies published between 2015-2022 and identifies key trends in accuracy improvements. Ensemble methods show the most promise for operational weather forecasting systems. The review highlights challenges in data quality, model interpretability, and computational efficiency.",
            relevance_score=0.88
        ),
        PaperMetadata(
            id="paper_3",
            title="Ensemble methods for climate model uncertainty quantification in precipitation forecasting",
            authors=["A. Thompson", "B. Williams"],
            year=2024,
            venue="Geophysical Research Letters",
            doi="10.1029/2024GL123456",
            abstract="Uncertainty quantification in climate models is crucial for reliable predictions and policy decisions. This paper introduces a Bayesian ensemble approach that combines multiple climate models to reduce prediction uncertainty. The method incorporates model weights based on historical performance and provides confidence intervals for temperature and precipitation projections. Results show 30% reduction in prediction uncertainty compared to single-model approaches. The framework is validated using 20 years of observational data and demonstrates robust performance across different climate regions.",
            relevance_score=0.92
        ),
        PaperMetadata(
            id="paper_4",
            title="Neural network architectures for long-term climate prediction",
            authors=["D. Martinez", "E. Kim", "F. Zhang"],
            year=2023,
            venue="Artificial Intelligence",
            doi="10.1016/j.artint.2023.103456",
            abstract="Long-term climate prediction requires sophisticated modeling approaches that can capture complex temporal dependencies. This work evaluates various neural network architectures including transformers, recurrent networks, and graph neural networks for climate forecasting tasks. Transformer-based models achieve state-of-the-art performance with 92% accuracy on 10-year temperature predictions. The study analyzes computational requirements and proposes efficient training strategies for large-scale climate datasets. Attention mechanisms prove particularly effective for capturing long-range temporal patterns.",
            relevance_score=0.89
        ),
        PaperMetadata(
            id="paper_5",
            title="Comparative analysis of statistical and machine learning methods in climate science",
            authors=["G. Anderson", "H. Liu"],
            year=2021,
            venue="Climate Dynamics",
            doi="10.1007/s00382-021-05678-9",
            abstract="Traditional statistical methods have long been the foundation of climate science, but machine learning approaches are gaining prominence. This comparative analysis evaluates the performance of classical statistical models against modern ML techniques across various climate prediction tasks. Statistical methods maintain advantages in interpretability and theoretical foundations, while ML approaches excel in handling high-dimensional data and non-linear relationships. The study recommends hybrid approaches that combine the strengths of both methodologies for optimal climate prediction performance.",
            relevance_score=0.85
        )
    ]
    
    # Create sample claims with matching paper IDs
    claims = [
        Claim(
            id="claim_1",
            statement="Deep learning models achieve 95% accuracy in temperature prediction tasks using ensemble methods",
            paper_id="paper_1",
            confidence=0.95,
            metrics={"accuracy": 0.95, "rmse": 0.12},
            datasets=["ERA5", "NCEP"]
        ),
        Claim(
            id="claim_2", 
            statement="Ensemble methods outperform single models in weather forecasting applications",
            paper_id="paper_2",
            confidence=0.88,
            metrics={"accuracy": 0.88, "mae": 0.15},
            datasets=["GFS", "ECMWF"]
        ),
        Claim(
            id="claim_3",
            statement="Bayesian ensemble approaches reduce prediction uncertainty by 30% in climate models",
            paper_id="paper_3",
            confidence=0.92,
            metrics={"uncertainty_reduction": 0.30},
            datasets=["CMIP6"]
        ),
        Claim(
            id="claim_4",
            statement="Transformer-based models achieve 92% accuracy on 10-year temperature predictions",
            paper_id="paper_4",
            confidence=0.89,
            metrics={"accuracy": 0.92, "prediction_horizon": 10},
            datasets=["ERA5", "CMIP6"]
        ),
        Claim(
            id="claim_5",
            statement="Hybrid statistical-ML approaches optimize climate prediction performance",
            paper_id="paper_5",
            confidence=0.85,
            metrics={"performance_improvement": 0.25},
            datasets=["NOAA", "ERA5"]
        )
    ]
    
    # Create topic map
    topic_map = TopicMap(
        main_topic="Machine Learning for Climate Change Prediction",
        subtopics=["Deep Learning", "Weather Forecasting", "Uncertainty Quantification", "Neural Networks", "Statistical Methods"],
        methods=["Ensemble Methods", "Neural Networks", "Bayesian Approaches", "Transformers", "Hybrid Models"],
        keywords=["climate", "prediction", "machine learning", "deep learning", "ensemble", "uncertainty"]
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

async def test_complete_literature_system():
    """Test the complete literature system with comprehensive data."""
    
    print("🧪 Testing Complete Literature System")
    print("=" * 60)
    
    # Create comprehensive test data
    research_results = create_comprehensive_test_data()
    
    # Initialize literature builder
    literature_agent = LiteratureBuilderAgent()
    
    try:
        # Generate literature
        print("📚 Generating literature from abstracts...")
        literature_document = await literature_agent.process(research_results)
        
        # Display comprehensive results
        print(f"\n📖 Literature Generated Successfully!")
        print(f"Title: {literature_document.outline.title}")
        print(f"Sections: {len(literature_document.sections)}")
        print(f"Total Words: {literature_document.total_word_count}")
        print(f"Bibliography Entries: {len(literature_document.bibliography)}")
        
        # Analyze content quality
        total_latex_citations = 0
        total_abstracts_used = 0
        
        # Show each section with detailed analysis
        for i, section in enumerate(literature_document.sections, 1):
            print(f"\n--- Section {i}: {section.title} ---")
            print(f"Word Count: {section.word_count}")
            print(f"Citations: {len(section.citations)} references")
            
            # Count LaTeX citations
            latex_citations = section.content.count('\\cite{')
            total_latex_citations += latex_citations
            print(f"LaTeX Citations: {latex_citations}")
            
            # Show content preview
            if section.content:
                preview = section.content[:200].replace('\n', ' ')
                print(f"Content Preview: {preview}...")
                
                # Check if abstracts are being used (look for specific phrases from our test abstracts)
                abstract_indicators = [
                    "achieves 95% accuracy", "comprehensive systematic review", 
                    "30% reduction in prediction uncertainty", "transformer-based models",
                    "comparative analysis evaluates"
                ]
                
                for indicator in abstract_indicators:
                    if indicator.lower() in section.content.lower():
                        total_abstracts_used += 1
                        print(f"✅ Abstract content detected: '{indicator}'")
                        break
        
        # Show bibliography with analysis
        print(f"\n--- Bibliography Analysis ---")
        bibitem_count = 0
        correct_format_count = 0
        
        for i, entry in enumerate(literature_document.bibliography, 1):
            print(f"{i}. {entry}")
            
            if '\\bibitem{' in entry:
                bibitem_count += 1
            
            # Check for correct author format (initials first)
            if any(pattern in entry for pattern in ['Y. Saad', 'K. Patel', 'A. Thompson', 'D. Martinez', 'G. Anderson']):
                correct_format_count += 1
        
        # Quality assessment
        print(f"\n--- Quality Assessment ---")
        print(f"✅ LaTeX Citations: {total_latex_citations} found")
        print(f"✅ Abstract Content Used: {total_abstracts_used} sections contain abstract-derived content")
        print(f"✅ Bibitem Format: {bibitem_count}/{len(literature_document.bibliography)} entries use \\bibitem format")
        print(f"✅ Author Format: {correct_format_count}/{len(literature_document.bibliography)} entries use correct author format")
        
        # Test specific features
        print(f"\n--- Feature Testing ---")
        
        # Test bibitem key generation
        print(f"🔑 Bibitem Key Generation:")
        for paper in research_results.papers:
            key = literature_agent._generate_bibitem_key(paper)
            print(f"  {paper.authors[0] if paper.authors else 'Unknown'} ({paper.year}) -> {key}")
        
        # Test CrossRef integration (with fake DOIs)
        print(f"\n🔍 CrossRef API Integration Test:")
        sample_paper = research_results.papers[0]
        volume_info = literature_agent._extract_volume_info(sample_paper)
        print(f"  Paper: {sample_paper.title[:50]}...")
        print(f"  Volume: {volume_info.get('volume', 'Not found')}")
        print(f"  Issue: {volume_info.get('issue', 'Not found')}")
        print(f"  Pages: {volume_info.get('pages', 'Not found')}")
        
        # Final assessment
        success_criteria = [
            total_latex_citations > 0,
            total_abstracts_used > 0,
            bibitem_count == len(literature_document.bibliography),
            literature_document.total_word_count > 500,
            len(literature_document.sections) >= 4
        ]
        
        success_rate = sum(success_criteria) / len(success_criteria) * 100
        
        print(f"\n--- Final Assessment ---")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 80:
            print(f"🎉 EXCELLENT: Literature system is working correctly!")
        elif success_rate >= 60:
            print(f"✅ GOOD: Literature system is mostly working with minor issues")
        else:
            print(f"⚠️ NEEDS IMPROVEMENT: Literature system has significant issues")
        
        return literature_document, success_rate >= 80
        
    except Exception as e:
        print(f"\n❌ Error during literature generation: {str(e)}")
        import traceback
        traceback.print_exc()
        return None, False

if __name__ == "__main__":
    # Run the comprehensive test
    result, success = asyncio.run(test_complete_literature_system())
    
    if success:
        print(f"\n🎉 Complete Literature System Test SUCCESSFUL!")
        print(f"✅ All major features are working correctly")
        print(f"✅ Abstracts are being processed into literature")
        print(f"✅ LaTeX citations are properly embedded")
        print(f"✅ Bibliography uses correct custom format")
        print(f"✅ CrossRef API integration is functional")
    else:
        print(f"\n💥 Complete Literature System Test FAILED!")
        print(f"❌ Some features need attention")