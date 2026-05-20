#!/usr/bin/env python3
"""
Simple test to check if research endpoint is working.
"""
import requests
import json

def test_research():
    """Test the research endpoint with a simple topic."""
    print("🧪 Testing Research Endpoint")
    print("=" * 30)
    
    try:
        # Test with a simple topic
        research_data = {
            "topic": "machine learning"
        }
        
        print(f"📤 Sending request: {research_data}")
        
        response = requests.post(
            'http://localhost:5000/research',
            json=research_data,
            timeout=120  # 2 minute timeout
        )
        
        print(f"📥 Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Research completed successfully!")
            print(f"   📄 Papers: {len(data.get('papers', []))}")
            print(f"   📝 Citations: {len(data.get('citations', []))}")
            print(f"   💡 Research gaps: {len(data.get('research_gaps', []))}")
            
            # Save response for debugging
            with open('debug_response.json', 'w') as f:
                json.dump(data, f, indent=2, default=str)
            print("   💾 Response saved to debug_response.json")
            
        else:
            print(f"❌ Research failed: {response.status_code}")
            print(f"   Error: {response.text}")
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out - this might be normal for first run")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_research()