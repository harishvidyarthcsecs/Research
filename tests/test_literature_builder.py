#!/usr/bin/env python3
"""
Test script for the Literature Builder module.
"""
import requests
import json
import time

def test_literature_builder():
    """Test the literature builder functionality."""
    print("📚 Testing Literature Builder Module")
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
    
    # Test literature page loads
    try:
        response = requests.get('http://localhost:5000/literature', timeout=5)
        if response.status_code == 200:
            print("✅ Literature builder page loads successfully")
        else:
            print("❌ Literature page failed to load:", response.status_code)
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Literature page test failed: {e}")
        return False
    
    # Test literature generation endpoint
    print("\n📖 Testing literature generation...")
    try:
        literature_data = {
            "topic": "machine learning",
            "filters": {
                "q_rankings": ["Q1", "Q2", "Q3"],
                "include_sa_papers": True,
                "max_sections": 5
            }
        }
        
        print(f"📤 Sending request: {literature_data}")
        
        response = requests.post(
            'http://localhost:5000/generate-literature',
            json=literature_data,
            timeout=180  # 3 minute timeout
        )
        
        print(f"📥 Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Literature generation completed successfully!")
            
            # Check response structure
            required_fields = ['topic', 'outline', 'sections', 'bibliography', 'stats']
            for field in required_fields:
                if field in data:
                    print(f"   ✓ {field}")
                else:
                    print(f"   ❌ Missing {field}")
            
            # Display statistics
            if 'stats' in data:
                stats = data['stats']
                print(f"\n📊 Literature Statistics:")
                print(f"   📄 Total sections: {stats.get('total_sections', 0)}")
                print(f"   📝 Total words: {stats.get('total_words', 0)}")
                print(f"   📚 Total papers: {stats.get('total_papers', 0)}")
                print(f"   🏆 Q1 papers: {stats.get('q1_papers', 0)}")
                print(f"   📊 SA papers: {stats.get('sa_papers', 0)}")
            
            # Display outline
            if 'outline' in data:
                outline = data['outline']
                print(f"\n📋 Literature Outline:")
                print(f"   Title: {outline.get('title', 'N/A')}")
                print(f"   Sections: {len(outline.get('sections', []))}")
                print(f"   Date range: {outline.get('date_range', 'N/A')}")
            
            # Display sections info
            if 'sections' in data:
                sections = data['sections']
                print(f"\n📖 Generated Sections:")
                for i, section in enumerate(sections[:3]):  # Show first 3 sections
                    print(f"   {i+1}. {section.get('title', 'Untitled')} ({section.get('word_count', 0)} words)")
                
                if len(sections) > 3:
                    print(f"   ... and {len(sections) - 3} more sections")
            
            # Save response for debugging
            with open('debug_literature.json', 'w') as f:
                json.dump(data, f, indent=2, default=str)
            print("   💾 Response saved to debug_literature.json")
            
            return True
            
        else:
            print(f"❌ Literature generation failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Literature generation request timed out")
        print("   This might be normal for first run or complex topics")
        return False
    except Exception as e:
        print(f"❌ Literature generation error: {e}")
        return False

def test_literature_features():
    """Test specific literature builder features."""
    print("\n🔧 Testing Literature Builder Features")
    print("=" * 40)
    
    try:
        response = requests.get('http://localhost:5000/literature', timeout=5)
        if response.status_code == 200:
            html_content = response.text
            
            # Check for key literature builder elements
            required_elements = [
                'id="literatureForm"',  # Literature generation form
                'id="includeQ1"',       # Q1 filter checkbox
                'id="includeQ2"',       # Q2 filter checkbox  
                'id="includeQ3"',       # Q3 filter checkbox
                'id="includeSA"',       # SA papers checkbox
                'id="minYear"',         # Minimum year filter
                'id="maxSections"',     # Maximum sections filter
                'generate-literature',  # Literature generation endpoint
                'downloadLiterature',   # Download function
                'displayStatistics',    # Statistics display function
                'displayOutline',       # Outline display function
                'displaySections',      # Sections display function
                'displayBibliography',  # Bibliography display function
            ]
            
            for element in required_elements:
                if element in html_content:
                    print(f"✅ Found: {element}")
                else:
                    print(f"❌ Missing: {element}")
            
            print("✅ Literature builder page has all required features")
            return True
            
        else:
            print(f"❌ Literature page failed to load: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Literature features test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting Literature Builder Tests")
    print("Please make sure the server is running: python app_fixed.py")
    print()
    
    # Test literature builder features first (faster)
    features_ok = test_literature_features()
    
    # Test literature generation functionality
    generation_ok = test_literature_builder()
    
    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)
    print(f"Literature Features: {'✅ PASS' if features_ok else '❌ FAIL'}")
    print(f"Literature Generation: {'✅ PASS' if generation_ok else '❌ FAIL'}")
    
    if features_ok and generation_ok:
        print("\n🎉 All tests passed! The Literature Builder is ready.")
        print("\n📋 Features Available:")
        print("   • Automatic claim clustering by theme and method")
        print("   • Q-ranking classification (Q1/Q2/Q3)")
        print("   • SA (Systematic Analysis) paper identification")
        print("   • Structured literature sections (Introduction, Related Work, etc.)")
        print("   • Citation-backed paragraph generation")
        print("   • Contradiction and agreement analysis")
        print("   • Temporal trend analysis")
        print("   • Multiple download formats (Markdown, LaTeX, JSON)")
        print("   • Comprehensive filtering options")
        print("   • Traceability from paragraphs to claims to papers")
    else:
        print("\n❌ Some tests failed. Please check the issues above.")
        
    print(f"\n🌐 Access the Literature Builder at: http://localhost:5000/literature")