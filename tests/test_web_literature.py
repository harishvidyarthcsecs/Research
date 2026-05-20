#!/usr/bin/env python3
"""
Test the web interface literature generation endpoint.
"""

import requests
import json
import time

def test_literature_endpoint():
    """Test the literature generation endpoint."""
    
    print("🌐 Testing Web Interface Literature Generation")
    print("=" * 50)
    
    # Test data
    test_data = {
        "topic": "machine learning climate prediction",
        "filters": {
            "q_rankings": ["Q1", "Q2", "Q3"],
            "include_sa_papers": True,
            "min_year": 2020,
            "max_sections": 10
        }
    }
    
    try:
        # Test the literature generation endpoint
        print("📡 Sending request to /generate-literature...")
        
        response = requests.post(
            "http://localhost:5000/generate-literature",
            json=test_data,
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            
            print("✅ Literature generation successful!")
            print(f"📊 Statistics:")
            print(f"  - Sections: {data['stats']['total_sections']}")
            print(f"  - Words: {data['stats']['total_words']}")
            print(f"  - Papers: {data['stats']['total_papers']}")
            print(f"  - Q1 Papers: {data['stats']['q1_papers']}")
            print(f"  - SA Papers: {data['stats']['sa_papers']}")
            
            print(f"\n📖 Outline: {data['outline']['title']}")
            
            print(f"\n📝 Sections:")
            for i, section in enumerate(data['sections'], 1):
                print(f"  {i}. {section['title']} ({section['word_count']} words)")
                if section['content']:
                    preview = section['content'][:100].replace('\n', ' ')
                    print(f"     Preview: {preview}...")
            
            print(f"\n📚 Bibliography ({len(data['bibliography'])} entries):")
            for i, entry in enumerate(data['bibliography'][:3], 1):
                print(f"  {i}. {entry[:80]}...")
            
            # Check for LaTeX citations
            has_latex_citations = any('\\cite{' in section['content'] for section in data['sections'])
            print(f"\n🔗 LaTeX Citations: {'✅ Found' if has_latex_citations else '❌ Not found'}")
            
            # Check for bibitem format
            has_bibitem = any('\\bibitem{' in entry for entry in data['bibliography'])
            print(f"📖 Bibitem Format: {'✅ Correct' if has_bibitem else '❌ Incorrect'}")
            
            return True
            
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to web server. Make sure it's running on localhost:5000")
        return False
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_literature_endpoint()
    
    if success:
        print(f"\n🎉 Web interface test successful!")
    else:
        print(f"\n💥 Web interface test failed!")
        print("Make sure the Flask app is running: python app_fixed.py")