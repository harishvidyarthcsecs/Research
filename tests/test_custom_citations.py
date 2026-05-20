"""
Test script for custom citation formatting.
"""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.agents.custom_citation_formatter import CustomCitationFormatter
from src.models.data_models import PaperMetadata


async def test_custom_citations():
    """Test custom citation formatting."""
    
    print("📖 Testing Custom Citation Formatting")
    print("=" * 50)
    
    # Create test papers
    test_papers = [
        PaperMetadata(
            title="Topological properties of hypercubes",
            authors=["Y. Saad", "M.H. Schultz"],
            year=1988,
            venue="IEEE Transactions on Computers",
            doi="10.48550/arXiv.1510.00800",
            abstract="This paper studies the topological properties of hypercube networks."
        ),
        PaperMetadata(
            title="The Wiener index of trees and its applications",
            authors=["Ivan Gutman", "Boris Furtula", "Xueliang Li"],
            year=2012,
            venue="Journal of Mathematical Chemistry",
            doi="10.1007/s10910-012-0018-7",
            abstract="We study the Wiener index and its mathematical properties."
        ),
        PaperMetadata(
            title="Graph neural networks for molecular property prediction",
            authors=["David K. Duvenaud", "Dougal Maclaurin", "Jorge Iparraguirre", "Rafael Bombarell"],
            year=2015,
            venue="Advances in Neural Information Processing Systems",
            arxiv_id="1509.09292",
            abstract="We present graph neural networks for predicting molecular properties."
        )
    ]
    
    # Test custom formatter
    formatter = CustomCitationFormatter()
    
    print("🔧 Generating custom citations...")
    citations = await formatter.process(test_papers)
    
    print(f"\n📊 Generated {len(citations)} citations")
    
    # Display citations
    print("\n📖 Custom Format Citations:")
    print("=" * 80)
    
    for i, citation in enumerate(citations, 1):
        print(f"\n{i}. Bibitem Key: {citation['bibitem_key']}")
        print(f"   Citation: {citation['bibitem_citation']}")
        print(f"   Paper URL: {citation['paper_url']}")
        print(f"   Journal: {citation['journal_name']}")
        print(f"   Year: {citation['year']}")
    
    # Test filtering
    print(f"\n🔍 Testing Filtering:")
    
    # Filter by journal
    ieee_citations = formatter.filter_citations(citations, journal_filter="IEEE")
    print(f"IEEE papers: {len(ieee_citations)}")
    
    # Filter by year
    recent_citations = formatter.filter_citations(citations, year_range=(2010, 2020))
    print(f"Papers 2010-2020: {len(recent_citations)}")
    
    # Generate bibliography
    print(f"\n📚 Complete Bibliography:")
    print("=" * 80)
    bibliography = formatter.generate_bibliography(citations)
    print(bibliography)
    
    # Get statistics
    stats = formatter.get_citation_stats(citations)
    print(f"\n📈 Citation Statistics:")
    print(f"Total citations: {stats['total_citations']}")
    print(f"Unique journals: {stats['unique_journals']}")
    print(f"Year range: {stats['year_range']}")
    print(f"Top journals: {stats['top_journals']}")
    
    print(f"\n✅ Custom citation formatting test completed!")


async def test_format_examples():
    """Test specific formatting examples."""
    
    print("\n🧪 Testing Format Examples")
    print("=" * 30)
    
    formatter = CustomCitationFormatter()
    
    # Test author formatting
    test_authors = [
        ["Y. Saad", "M.H. Schultz"],
        ["Ivan Gutman"],
        ["David K. Duvenaud", "Dougal Maclaurin", "Jorge Iparraguirre"]
    ]
    
    print("👥 Author Formatting:")
    for authors in test_authors:
        formatted = formatter._format_authors_custom(authors)
        print(f"   {authors} → {formatted}")
    
    # Test title formatting
    test_titles = [
        "Topological properties of hypercubes",
        "The Wiener index of trees and its applications",
        "Graph neural networks for molecular property prediction",
        "COVID-19 detection using machine learning: A comprehensive study"
    ]
    
    print("\n📝 Title Formatting:")
    for title in test_titles:
        formatted = formatter._format_title_custom(title)
        print(f"   '{title}' → '{formatted}'")
    
    # Test bibitem key generation
    test_paper = PaperMetadata(
        title="Test paper",
        authors=["Y. Saad", "M.H. Schultz"],
        year=1988,
        venue="Test Journal",
        abstract="Test abstract"
    )
    
    bibitem_key = formatter._generate_bibitem_key(test_paper)
    print(f"\n🔑 Bibitem Key: {bibitem_key}")
    
    print("✅ Format examples test completed!")


if __name__ == "__main__":
    print("🚀 Custom Citation System Test")
    print("Testing the new citation format and filtering system")
    print()
    
    # Run tests
    asyncio.run(test_custom_citations())
    asyncio.run(test_format_examples())
    
    print("\n💡 Next steps:")
    print("1. Open web interface: http://localhost:5000/citations")
    print("2. Enter a research topic")
    print("3. See custom formatted citations")
    print("4. Use filters and download options")