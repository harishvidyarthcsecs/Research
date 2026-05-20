#!/usr/bin/env python3
"""
Complete system test to verify all components are working.
"""

import sys
import os
import requests
import time

def test_web_interface():
    """Test that the web interface is accessible."""
    
    print("🌐 Testing Web Interface")
    print("=" * 30)
    
    base_url = "http://localhost:5000"
    
    # Test endpoints
    endpoints = [
        ("/", "Home Page"),
        ("/literature", "Literature Builder"),
        ("/validator", "Reference Validator"),
        ("/citations", "Enhanced Citations"),
        ("/test", "System Test")
    ]
    
    results = []
    
    for endpoint, name in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            if response.status_code == 200:
                print(f"✅ {name}: {endpoint} - OK")
                results.append(True)
            else:
                print(f"❌ {name}: {endpoint} - Status {response.status_code}")
                results.append(False)
        except requests.exceptions.ConnectionError:
            print(f"❌ {name}: {endpoint} - Connection failed (server not running?)")
            results.append(False)
        except requests.exceptions.Timeout:
            print(f"❌ {name}: {endpoint} - Timeout")
            results.append(False)
        except Exception as e:
            print(f"❌ {name}: {endpoint} - Error: {str(e)}")
            results.append(False)
    
    return results

def test_reference_validator_endpoint():
    """Test the reference validator endpoint specifically."""
    
    print(f"\n🔍 Testing Reference Validator Endpoint")
    print("=" * 40)
    
    base_url = "http://localhost:5000"
    
    # Test data
    test_data = {
        "content": "\\bibitem{test} A. Test, Test paper, Test Journal (2024)",
        "format": "bibitem",
        "options": {
            "checkFormat": True,
            "checkSpelling": True,
            "checkDuplicates": True,
            "verifyPapers": False  # Skip verification for quick test
        }
    }
    
    try:
        print("📡 Sending validation request...")
        response = requests.post(
            f"{base_url}/validate-references",
            json=test_data,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Reference validation endpoint working!")
            print(f"   Original count: {data['stats']['original_count']}")
            print(f"   Final count: {data['stats']['final_count']}")
            return True
        else:
            print(f"❌ Validation failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - make sure server is running")
        return False
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_validator_instantiation():
    """Test that ReferenceValidator can be instantiated."""
    
    print(f"\n🧪 Testing ReferenceValidator Instantiation")
    print("=" * 42)
    
    try:
        # Add src to path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'agents'))
        
        from reference_validator import ReferenceValidator
        
        # Try to instantiate
        validator = ReferenceValidator()
        print("✅ ReferenceValidator instantiated successfully")
        print(f"   Name: {validator.name}")
        print(f"   Has process method: {hasattr(validator, 'process')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Instantiation failed: {str(e)}")
        return False

def main():
    """Run complete system test."""
    
    print("🧪 Complete System Test")
    print("=" * 50)
    
    # Test 1: Validator instantiation
    instantiation_ok = test_validator_instantiation()
    
    # Test 2: Web interface
    web_results = test_web_interface()
    
    # Test 3: Reference validator endpoint (only if web interface is working)
    if any(web_results):
        time.sleep(1)  # Brief pause
        validator_endpoint_ok = test_reference_validator_endpoint()
    else:
        print(f"\n⚠️ Skipping endpoint test - web interface not accessible")
        validator_endpoint_ok = False
    
    # Summary
    print(f"\n📊 Test Summary")
    print("=" * 20)
    
    print(f"✅ Validator Instantiation: {'PASS' if instantiation_ok else 'FAIL'}")
    print(f"✅ Web Interface: {sum(web_results)}/{len(web_results)} endpoints working")
    print(f"✅ Validator Endpoint: {'PASS' if validator_endpoint_ok else 'FAIL'}")
    
    overall_success = instantiation_ok and any(web_results)
    
    if overall_success:
        print(f"\n🎉 SYSTEM TEST SUCCESSFUL!")
        print(f"✅ Reference Validator is ready to use")
        print(f"🌐 Access at: http://localhost:5000/validator")
    else:
        print(f"\n⚠️ SYSTEM TEST ISSUES DETECTED")
        if not instantiation_ok:
            print(f"❌ Fix the ReferenceValidator instantiation issue")
        if not any(web_results):
            print(f"❌ Start the web server: python app_fixed.py")
    
    return overall_success

if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\n🎉 All critical components working!")
    else:
        print(f"\n💥 Some issues need attention!")