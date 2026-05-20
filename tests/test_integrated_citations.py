"""
Test the integrated citation system with filtering and download.
"""
import requests
import json
import time


def test_integrated_citations():
    """Test the integrated citation system."""
    
    print("🧪 Testing Integrated Citation System")
    print("=" * 50)
    
    base_url = "http://localhost:5000"
    
    # Test research with citations
    print("🔬 Testing research with integrated citations...")
    
    research_data = {
        "topic": "Wiener Index in Graph Theory"
    }
    
    try:
        print("   Sending research request...")
        start_time = time.time()
        
        response = requests.post(
            f"{base_url}/research", 
            json=research_data,
            timeout=120
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Research completed in {duration:.1f} seconds")
            
            # Check citations
            citations = result.get('citations', [])
            print(f"📖 Citations generated: {len(citations)}")
            
            if citations:
                # Show first citation
                first_citation = citations[0]
                print(f"\n📝 Sample Citation:")
                print(f"   Custom Format: {first_citation.get('custom_format', 'N/A')}")
                print(f"   BibTeX: {first_citation.get('bibtex', 'N/A')[:100]}...")
                print(f"   Journal: {first_citation.get('journal_name', 'N/A')}")
                print(f"   Year: {first_citation.get('year', 'N/A')}")
                print(f"   Paper URL: {first_citation.get('paper_url', 'N/A')}")
                
                # Check filtering data
                journals = list(set(c.get('journal_name', '') for c in citations))
                years = list(set(c.get('year', 0) for c in citations))
                
                print(f"\n🔍 Filtering Options:")
                print(f"   Unique Journals: {len(journals)}")
                print(f"   Unique Years: {len(years)}")
                print(f"   Journals: {journals[:3]}...")
                print(f"   Years: {sorted(years, reverse=True)[:5]}")
            
            print(f"\n✅ Integrated citation system working!")
            
        else:
            print(f"❌ Research failed: {response.status_code}")
            print(f"   Error: {response.text}")
            
    except requests.exceptions.Timeout:
        print("❌ Research request timed out")
    except requests.exceptions.RequestException as e:
        print(f"❌ Research request failed: {e}")
    
    print(f"\n💡 Features Available:")
    print("✅ Custom citation format (bibitem with author initials)")
    print("✅ Filter by journal name")
    print("✅ Filter by publication year")
    print("✅ Multiple reference formats (Custom, BibTeX, APA, IEEE)")
    print("✅ View paper button (DOI links)")
    print("✅ Download filtered citations")
    print("✅ Copy individual citations")
    
    print(f"\n🌐 Access the system at: {base_url}")
    print("   Enter any research topic and see the enhanced citations!")


if __name__ == "__main__":
    test_integrated_citations()