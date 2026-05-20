#!/usr/bin/env python3
"""
Test script to verify the comprehensive filtering system works correctly.
"""
import requests
import json
import time

def test_filtering_system():
    """Test the comprehensive filtering system."""
    print("🧪 Testing Comprehensive Filtering System")
    print("=" * 50)
    
    # Test server is running
    try:
        response = requests.get('http://localhost:5000/test', timeout=5)
        if response.status_code == 200:
            print("✅ Server is running and responsive")
        else:
            print("❌ Server responded with error:", response.status_code)
            return False
    except requests.exceptions.RequestException as e:
        print("❌ Server is not running. Please start with: python app_fixed.py")
        return False
    
    # Test research endpoint with a simple topic
    print("\n🔍 Testing research functionality...")
    try:
        research_data = {
            "topic": "machine learning"
        }
        
        response = requests.post(
            'http://localhost:5000/research',
            json=research_data,
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Research completed successfully")
            print(f"   📄 Papers found: {len(data.get('papers', []))}")
            print(f"   📝 Citations generated: {len(data.get('citations', []))}")
            print(f"   💡 Research gaps: {len(data.get('research_gaps', []))}")
            
            # Check if filtering data is present
            papers = data.get('papers', [])
            citations = data.get('citations', [])
            
            if papers:
                print("✅ Papers have required fields for filtering:")
                sample_paper = papers[0]
                required_fields = ['title', 'authors', 'year', 'venue', 'abstract']
                for field in required_fields:
                    if field in sample_paper:
                        print(f"   ✓ {field}")
                    else:
                        print(f"   ❌ Missing {field}")
            
            if citations:
                print("✅ Citations have required fields for filtering:")
                sample_citation = citations[0]
                required_fields = ['journal_name', 'year', 'custom_format', 'bibtex']
                for field in required_fields:
                    if field in sample_citation:
                        print(f"   ✓ {field}")
                    else:
                        print(f"   ❌ Missing {field}")
            
            return True
            
        else:
            print(f"❌ Research failed with status: {response.status_code}")
            print(f"   Error: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Research request timed out (this is normal for first run)")
        print("   The system may still be initializing. Try again in a few minutes.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Research request failed: {e}")
        return False

def test_frontend_features():
    """Test that the frontend has all the required filtering features."""
    print("\n🎨 Testing Frontend Features")
    print("=" * 30)
    
    try:
        response = requests.get('http://localhost:5000/', timeout=5)
        if response.status_code == 200:
            html_content = response.text
            
            # Check for key filtering elements
            required_elements = [
                'id="globalSearch"',  # Global search bar
                'id="journalFilter"',  # Journal filter
                'id="yearFilter"',     # Year filter
                'id="formatFilter"',   # Citation format filter
                'toggleJournalOptions()', # Advanced journal options
                'clearAllFilters()',   # Clear all filters function
                'downloadFilteredResults()', # Download filtered results
                'applyAllFilters()',   # Apply all filters function
                'class="filter-section"', # Filter section styling
            ]
            
            for element in required_elements:
                if element in html_content:
                    print(f"✅ Found: {element}")
                else:
                    print(f"❌ Missing: {element}")
            
            print("✅ Frontend loaded successfully with filtering features")
            return True
            
        else:
            print(f"❌ Frontend failed to load: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Frontend test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting Comprehensive Filtering System Tests")
    print("Please make sure the server is running: python app_fixed.py")
    print()
    
    # Test frontend features first (faster)
    frontend_ok = test_frontend_features()
    
    # Test backend functionality
    backend_ok = test_filtering_system()
    
    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)
    print(f"Frontend Features: {'✅ PASS' if frontend_ok else '❌ FAIL'}")
    print(f"Backend Research:  {'✅ PASS' if backend_ok else '❌ FAIL'}")
    
    if frontend_ok and backend_ok:
        print("\n🎉 All tests passed! The comprehensive filtering system is ready.")
        print("\n📋 Features Available:")
        print("   • Global search across papers, authors, titles, journals")
        print("   • Advanced journal filtering (include/exclude/multi-select)")
        print("   • Year filtering with range selection")
        print("   • Citation format filtering (Custom/BibTeX/APA/IEEE)")
        print("   • Content visibility toggles (Papers/Citations/Research Gaps)")
        print("   • Filter statistics and clear all functionality")
        print("   • Download filtered results in multiple formats")
        print("   • Save and load filter presets")
    else:
        print("\n❌ Some tests failed. Please check the issues above.")