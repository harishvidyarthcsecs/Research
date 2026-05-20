"""
Test the complete citation format with corrected author formatting.
"""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.agents.custom_citation_formatter import CustomCitationFormatter
from src.models.data_models import PaperMetadata


async def test_complete_citation():
    """Test complete citation with corrected author format."""
    
    print("📖 Testing Complete Citation Format")
    print("=" * 60)
    
    # Create test paper matching your example
    test_paper = PaperMetadata(
        title="Topological properties of hypercubes",
        authors=["Y. Saad", "M.H. Schultz"],
        year=1988,
        venue="IEEE Transactions on Computers",
        doi="10.48550/arXiv.1510.00800",
        abstract="This paper studies the topological properties of hypercube networks."
    )
    
    # Test custom formatter
    formatter = CustomCitationFormatter()
    citations = await formatter.process([test_paper])
    
    if citations:
        citation = citations[0]
        
        print("🎯 Your Requested Format:")
        print("\\bibitem{SaSc88} Y. Saad, M.H. Schultz, Topological properties of hypercubes, IEEE Transactions on Computers \\textbf{37}(7) (1988) 867--872. https://doi.org/10.48550/arXiv.1510.00800")
        
        print("\n✅ Generated Format:")
        print(citation['bibitem_citation'])
        
        print(f"\n🔍 Format Breakdown:")
        print(f"   Bibitem Key: {citation['bibitem_key']}")
        print(f"   Authors: {citation['formatted_authors']}")
        print(f"   Title: {citation['formatted_title']}")
        print(f"   Journal: {citation['journal_name']}")
        print(f"   Year: {citation['year']}")
        print(f"   DOI Link: {citation['doi_link']}")
        
        print(f"\n✅ Author Format Verification:")
        print(f"   Expected: Y. Saad, M.H. Schultz")
        print(f"   Generated: {citation['formatted_authors']}")
        
        if citation['formatted_authors'] == "Y. Saad, M.H. Schultz":
            print("   🎉 PERFECT MATCH!")
        else:
            print("   ⚠️  Format difference detected")
    
    print(f"\n🌐 Test in Web Interface:")
    print("1. Go to: http://localhost:5000")
    print("2. Search: 'Topological properties hypercubes'")
    print("3. See citations with correct author format")
    print("4. Use filters and download functionality")


if __name__ == "__main__":
    asyncio.run(test_complete_citation())