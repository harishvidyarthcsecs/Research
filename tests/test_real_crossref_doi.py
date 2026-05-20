#!/usr/bin/env python3
"""
Test with a real DOI that should return actual CrossRef data.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import data models
from models.data_models import PaperMetadata

# Import app functions
import app_fixed

def create_paper_with_journal_doi():
    """Create test paper with a real journal DOI that should have volume/issue data."""
    
    # Using a real journal DOI that should exist in CrossRef
    paper = PaperMetadata(
        id="test_journal_paper",
        title="Deep learning",
        authors=["Y. LeCun", "Y. Bengio", "G. Hinton"],
        year=2015,
        venue="Nature",
        doi="10.1038/nature14539",  # Real Nature DOI
        abstract="Deep learning allows computational models that are composed of multiple processing layers to learn representations of data with multiple levels of abstraction.",
        relevance_score=0.99
    )
    
    return paper

def test_real_crossref_data():
    """Test with a real DOI that should return CrossRef data."""
    print("🔍 Testing with Real Journal DOI")
    print("=" * 40)
    
    paper = create_paper_with_journal_doi()
    
    print(f"Paper: {paper.title}")
    print(f"DOI: {paper.doi}")
    print(f"Venue: {paper.venue}")
    
    # Test volume info extraction
    print(f"\n📊 Extracting bibliographic data...")
    volume_info = app_fixed._extract_volume_info_crossref(paper)
    
    print(f"Results:")
    print(f"  Volume: {volume_info['volume'] or 'Not found'}")
    print(f"  Issue: {volume_info['issue'] or 'Not found'}")
    print(f"  Pages: {volume_info['pages'] or 'Not found'}")
    print(f"  Article Number: {volume_info['article_number'] or 'Not found'}")
    
    # Generate full citation
    print(f"\n📖 Generated Citation:")
    citation = app_fixed._generate_custom_citation(paper)
    print(f"{citation}")
    
    # Analyze results
    print(f"\n📋 Analysis:")
    if volume_info['volume'] and volume_info['volume'] != '1':
        print(f"✅ Real volume data found: {volume_info['volume']}")
    else:
        print(f"ℹ️ No volume data found")
    
    if volume_info['issue'] and volume_info['issue'] != '1':
        print(f"✅ Real issue data found: {volume_info['issue']}")
    else:
        print(f"ℹ️ No issue data found")
    
    if volume_info['pages'] and volume_info['pages'] not in ['1--10', None]:
        print(f"✅ Real page data found: {volume_info['pages']}")
    else:
        print(f"ℹ️ No page data found")
    
    # Check if citation contains fake data
    has_fake_volume = "\\textbf{1}(1)" in citation
    has_fake_pages = " 1--10" in citation
    
    if has_fake_volume or has_fake_pages:
        print(f"⚠️ Citation contains fake data")
    else:
        print(f"✅ Citation uses only real data or omits missing data")
    
    return volume_info

if __name__ == "__main__":
    try:
        volume_info = test_real_crossref_data()
        
        print(f"\n🎉 Test completed successfully!")
        
        if any(volume_info.values()):
            print(f"✅ CrossRef API returned real bibliographic data")
        else:
            print(f"ℹ️ No data returned (may be normal depending on DOI)")
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()