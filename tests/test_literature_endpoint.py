#!/usr/bin/env python3
"""
Quick test for the literature generation endpoint.
"""
import requests
import json

def test_literature_endpoint():
    """Test the literature generation endpoint."""
    print("🧪 Testing Literature Generation Endpoint")
    print("=" * 45)
    
    try:
        # Test with a simple topic
        literature_data = {
            "topic": "machine learning",
            "filters": {
                "q_rankings": ["Q1", "Q2", "Q3"],
                "include_sa_papers": True,
                "max_sections": 3
            }
        }
        
        print(f"📤 Sending request: {literature_data}")
        
        response = requests.post(
            'http://localhost:5000/generate-literature',
            json=literature_data,
            timeout=60  # 1 minute timeout for quick test
        )
        
        print(f"📥 Response status: {response.status_code}")
        print(f"📥 Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print("✅ Literature generation successful!")
                print(f"   Topic: {data.get('topic', 'N/A')}")
                print(f"   Sections: {len(data.get('sections', []))}")
                return True
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error: {e}")
                print(f"   Response content: {response.text[:500]}...")
                return False
        else:
            print(f"❌ Literature generation failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_literature_endpoint()