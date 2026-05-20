"""
Test script to verify the web API works correctly.
"""
import requests
import json
import time


def test_web_interface():
    """Test the web interface API."""
    base_url = "http://localhost:5000"
    
    print("🧪 Testing Web Interface API")
    print("=" * 40)
    
    # Test 1: Check if server is running
    try:
        response = requests.get(f"{base_url}/test", timeout=10)
        if response.status_code == 200:
            print("✅ Server is running")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Server test failed: {response.status_code}")
            return
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to server: {e}")
        print("   Make sure to run: python app_fixed.py")
        return
    
    # Test 2: Perform research
    print("\n🔬 Testing research functionality...")
    research_data = {
        "topic": "Machine Learning for Climate Prediction"
    }
    
    try:
        print("   Sending research request...")
        start_time = time.time()
        
        response = requests.post(
            f"{base_url}/research", 
            json=research_data,
            timeout=120  # 2 minute timeout
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Research completed in {duration:.1f} seconds")
            print(f"   Topic: {result['topic']}")
            print(f"   Papers found: {result['summary']['papers_analyzed']}")
            print(f"   Claims extracted: {result['summary']['claims_extracted']}")
            print(f"   Research gaps: {result['summary']['research_gaps_identified']}")
            
            # Test download link
            if 'download_url' in result:
                download_response = requests.get(f"{base_url}{result['download_url']}")
                if download_response.status_code == 200:
                    print("✅ Download functionality works")
                else:
                    print("❌ Download failed")
            
        else:
            print(f"❌ Research failed: {response.status_code}")
            print(f"   Error: {response.text}")
            
    except requests.exceptions.Timeout:
        print("❌ Research request timed out")
    except requests.exceptions.RequestException as e:
        print(f"❌ Research request failed: {e}")
    
    # Test 3: Check history
    print("\n📚 Testing history functionality...")
    try:
        response = requests.get(f"{base_url}/history", timeout=10)
        if response.status_code == 200:
            history = response.json()
            print(f"✅ History retrieved: {len(history)} previous research sessions")
            if history:
                print(f"   Latest: {history[0]['topic']}")
        else:
            print(f"❌ History failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ History request failed: {e}")
    
    print("\n🎉 Web interface testing completed!")
    print("💡 Now you can use the web interface at: http://localhost:5000")


if __name__ == "__main__":
    test_web_interface()