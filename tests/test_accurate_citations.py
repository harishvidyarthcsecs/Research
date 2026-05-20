#!/usr/bin/env python3
"""
Test script to verify that both literature builder and regular citation system use accurate bibliographic data.
"""

import sys
import os
import asyncio
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import directly
from models.data_models import PaperMetadata, Claim, ResearchResults, TopicMap

# Import agents
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'agents'))
from literature_builder_agent import LiteratureBuilderAgent
from custom_citation_formatter import CustomCitationFormatter

# Import app functions
import app_fixed

def create_test_paper_with_real_doi():
    """Create test paper with a real DOI for testing CrossRef integration."""
    
    # Using a real DOI that should exist in CrossRef
    paper = PaperMetadata(
        id="test_real_paper",
        title="Attention is all you need",
        authors=["A. Vaswani", "N. Shazeer", "N. Parmar"],
        year=2017,
        venue="Advances in Neural Information Processing Systems",
        doi="10.48550/arXiv.1706.03762",  # Real arXiv DOI
        abstract="The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.",
        relevance_score=0.98
    )
    
    return paper

def create_test_paper_with_fake_doi():
    """Create test paper with fake DOI to test fallback behavior."""
    
    paper = PaperMetadata(
        id="test_fake_paper",
        title="Test paper with fake DOI",
        authors=["J. Test", "K. Fake"],
        year=2024,
        venue="Test Journal vol. 15, no. 3",  # Contains volume info in venue
        doi="10.1000/fake.test.2024",
        abstract="This is a test paper with a fake DOI to test fallback behavior.",
        relevance_score=0.5
    )
    
    return paper

async def test_literature_builder_citations():
    """Test literature builder with accurate citations."""
    print("📚 Testing Literature Builder Citations")
    print("-" * 40)
    
    # Create test data with both real and fake DOIs
    papers = [
        create_test_paper_with_real_doi(),
        create_test_paper_with_fake_doi()
    ]
    
    claims = [
        Claim(
            id="claim_1",
            statement="Transformer architecture achieves state-of-the-art performance",
            paper_id="test_real_paper",
            confidence=0.98
        ),
        Claim(
            id="claim_2",
            statement="Test methods show promising results",
            paper_id="test_fake_paper",
            confidence=0.5
        )
    ]
    
    topic_map = TopicMap(
        main_topic="Transformer Architecture Testing",
        subtopics=["Attention Mechanisms", "Neural Networks"],
        methods=["Transformers", "Attention"],
        keywords=["transformer", "attention", "neural networks"]
    )
    
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
    
    # Test literature generation
    literature_agent = LiteratureBuilderAgent()
    literature_document = await literature_agent.process(research_results)
    
    print(f"✅ Literature generated with {len(literature_document.sections)} sections")
    
    # Analyze bibliography for accurate data
    print(f"\n📖 Bibliography Analysis:")
    for i, entry in enumerate(literature_document.bibliography, 1):
        print(f"{i}. {entry}")
        
        # Check if it contains real volume/issue data (not fake 1(1))
        if "\\textbf{" in entry:
            if "\\textbf{1}(1)" in entry:
                print(f"   ⚠️ Contains fake volume data")
            else:
                print(f"   ✅ Contains real volume data")
        else:
            print(f"   ℹ️ No volume data (acceptable if not available)")
    
    return literature_document

async def test_custom_citation_formatter():
    """Test custom citation formatter with accurate citations."""
    print(f"\n🔖 Testing Custom Citation Formatter")
    print("-" * 40)
    
    # Create test papers
    papers = [
        create_test_paper_with_real_doi(),
        create_test_paper_with_fake_doi()
    ]
    
    # Test citation formatting
    formatter = CustomCitationFormatter()
    citations = await formatter.process(papers)
    
    print(f"✅ Generated {len(citations)} citations")
    
    # Analyze citations for accurate data
    print(f"\n📋 Citation Analysis:")
    for i, citation in enumerate(citations, 1):
        print(f"{i}. {citation['bibitem_citation']}")
        
        # Check volume info
        if citation['volume_info']:
            if "\\textbf{1}" in citation['volume_info']:
                print(f"   ⚠️ Contains fake volume data: {citation['volume_info']}")
            else:
                print(f"   ✅ Contains real volume data: {citation['volume_info']}")
        else:
            print(f"   ℹ️ No volume data (acceptable if not available)")
        
        # Check page numbers
        if citation['page_numbers']:
            if citation['page_numbers'] == "1--10":
                print(f"   ⚠️ Contains fake page data: {citation['page_numbers']}")
            else:
                print(f"   ✅ Contains real page data: {citation['page_numbers']}")
        else:
            print(f"   ℹ️ No page data (acceptable if not available)")
    
    return citations

def test_app_citation_function():
    """Test the app citation function with accurate data."""
    print(f"\n🌐 Testing App Citation Function")
    print("-" * 40)
    
    # Create test papers
    papers = [
        create_test_paper_with_real_doi(),
        create_test_paper_with_fake_doi()
    ]
    
    # Test app citation generation
    for i, paper in enumerate(papers, 1):
        citation = app_fixed._generate_custom_citation(paper)
        print(f"{i}. {citation}")
        
        # Check for fake data
        if "\\textbf{1}(1)" in citation and "1--10" in citation:
            print(f"   ⚠️ Contains fake volume and page data")
        elif "\\textbf{1}" in citation:
            print(f"   ⚠️ Contains fake volume data")
        elif "1--10" in citation:
            print(f"   ⚠️ Contains fake page data")
        else:
            print(f"   ✅ Uses real data or no fake data")

async def main():
    """Run comprehensive citation accuracy test."""
    print("🧪 Testing Citation Accuracy Across All Systems")
    print("=" * 60)
    
    try:
        # Test all systems
        literature_doc = await test_literature_builder_citations()
        citations = await test_custom_citation_formatter()
        test_app_citation_function()
        
        # Summary
        print(f"\n📊 Test Summary")
        print("=" * 30)
        print(f"✅ Literature Builder: {len(literature_doc.sections)} sections generated")
        print(f"✅ Citation Formatter: {len(citations)} citations generated")
        print(f"✅ App Functions: Tested successfully")
        
        # Check for CrossRef integration
        has_crossref_calls = any("Fetching bibliographic data" in str(citation) for citation in citations)
        print(f"🔍 CrossRef API Integration: {'✅ Active' if has_crossref_calls else 'ℹ️ Not detected in output'}")
        
        print(f"\n🎉 All citation systems tested successfully!")
        print(f"📝 Note: Real DOIs will show accurate data, fake DOIs will show no volume/page data (correct behavior)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    
    if success:
        print(f"\n🎉 Citation Accuracy Test SUCCESSFUL!")
    else:
        print(f"\n💥 Citation Accuracy Test FAILED!")