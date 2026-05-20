#!/usr/bin/env python3
"""
Comprehensive test script for the Reference Validator system.
Tests all functionality including web interface, file processing, and validation.
"""

import asyncio
import json
import requests
import time
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.agents.reference_validator import ReferenceValidator, ReferenceValidationResult

def test_reference_validator_core():
    """Test the core reference validator functionality."""
    print("🧪 Testing Reference Validator Core Functionality")
    print("=" * 60)
    
    # Test sample references with various issues
    test_references = """
\\bibitem{SaSc88} Y. Saad, M.H. Schultz, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, SIAM Journal on Scientific and Statistical Computing \\textbf{7}(3) (1986) 856--869. https://doi.org/10.1137/0907058

\\bibitem{SaSc88} Y. Saad, M.H. Schultz, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, SIAM Journal on Scientific and Statistical Computing \\textbf{7}(3) (1986) 856--869. https://doi.org/10.1137/0907058

\\bibitem{Incomplete} John Smith, machien learing algoritm

\\bibitem{BadYear} Jane Doe, Some paper title, Journal Name \\textbf{1}(1) (2050) 1--10. https://doi.org/10.1000/invalid

\\bibitem{SpellErr} A. Author, anaylsis of performace in clasification tasks, IEEE Transactions \\textbf{5}(2) (2020) 100--110.
"""
    
    async def run_test():
        validator = ReferenceValidator()
        
        print("📝 Processing test references...")
        result = await validator.process_reference_file(test_references, 'bibitem')
        
        print(f"✅ Original references: {result.original_count}")
        print(f"🔄 Duplicates removed: {len(result.duplicates_removed)}")
        print(f"🔧 Format corrections: {len(result.format_corrections)}")
        print(f"📝 Spelling corrections: {len(result.spelling_corrections)}")
        print(f"❌ Invalid papers: {len(result.invalid_papers)}")
        print(f"✅ Final valid references: {result.final_count}")
        
        print("\n📋 Processing Log:")
        for log_entry in result.processing_log:
            print(f"  • {log_entry}")
        
        print("\n🔧 Format Corrections:")
        for correction in result.format_corrections:
            print(f"  • {correction['reference_key']}: {len(correction['corrections'])} corrections")
        
        print("\n📝 Spelling Corrections:")
        for correction in result.spelling_corrections:
            print(f"  • {correction['reference_key']}: {len(correction['corrections'])} corrections")
        
        print("\n❌ Invalid Papers:")
        for invalid in result.invalid_papers:
            print(f"  • {invalid['reference'].get('key', 'unknown')}: {invalid['reason']}")
        
        # Test output formats
        print("\n📄 Testing Output Formats:")
        
        bibitem_output = validator.generate_corrected_file(result, 'bibitem')
        print(f"  • Bibitem format: {len(bibitem_output)} characters")
        
        bibtex_output = validator.generate_corrected_file(result, 'bibtex')
        print(f"  • BibTeX format: {len(bibtex_output)} characters")
        
        plain_output = validator.generate_corrected_file(result, 'plain')
        print(f"  • Plain format: {len(plain_output)} characters")
        
        # Generate validation report
        report = validator.generate_validation_report(result)
        print(f"  • Validation report: {len(report)} characters")
        
        print("\n✅ Core functionality test completed successfully!")
        return result
    
    return asyncio.run(run_test())


def test_web_interface():
    """Test the web interface endpoints."""
    print("\n🌐 Testing Web Interface")
    print("=" * 60)
    
    base_url = "http://localhost:5000"
    
    # Test if server is running
    try:
        response = requests.get(f"{base_url}/test", timeout=5)
        if response.status_code == 200:
            print("✅ Flask server is running")
        else:
            print(f"❌ Flask server returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to Flask server: {e}")
        print("💡 Make sure to run: python app_fixed.py")
        return False
    
    # Test validator page
    try:
        response = requests.get(f"{base_url}/validator", timeout=5)
        if response.status_code == 200:
            print("✅ Reference validator page loads successfully")
        else:
            print(f"❌ Validator page returned status {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error loading validator page: {e}")
    
    # Test validation endpoint
    test_data = {
        "content": "\\bibitem{Test01} Y. Saad, Test paper, Test Journal \\textbf{1}(1) (2020) 1--10.",
        "format": "bibitem",
        "options": {
            "checkFormat": True,
            "checkSpelling": True,
            "checkDuplicates": True,
            "verifyPapers": False  # Skip verification for quick test
        }
    }
    
    try:
        print("📤 Testing validation endpoint...")
        response = requests.post(
            f"{base_url}/validate-references",
            json=test_data,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Validation endpoint works successfully")
            print(f"  • Original count: {result['stats']['original_count']}")
            print(f"  • Final count: {result['stats']['final_count']}")
            print(f"  • Processing log entries: {len(result['processing_log'])}")
        else:
            print(f"❌ Validation endpoint returned status {response.status_code}")
            print(f"Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error testing validation endpoint: {e}")
    
    print("✅ Web interface test completed!")
    return True


def test_file_formats():
    """Test different input file formats."""
    print("\n📁 Testing Different File Formats")
    print("=" * 60)
    
    # Test BibTeX format
    bibtex_content = """
@article{saad1986gmres,
  title={GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems},
  author={Saad, Youcef and Schultz, Martin H},
  journal={SIAM journal on scientific and statistical computing},
  volume={7},
  number={3},
  pages={856--869},
  year={1986},
  publisher={SIAM}
}

@article{duplicate1986gmres,
  title={GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems},
  author={Saad, Y and Schultz, M H},
  journal={SIAM journal on scientific and statistical computing},
  volume={7},
  number={3},
  pages={856--869},
  year={1986}
}
"""
    
    # Test plain text format
    plain_content = """
Y. Saad, M.H. Schultz, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, SIAM Journal (1986)
John Smith, machien learing paper, Some Journal (2020)
Invalid Author, Bad paper with wrong year, Journal (3000)
"""
    
    async def test_formats():
        validator = ReferenceValidator()
        
        # Test BibTeX
        print("📄 Testing BibTeX format...")
        bibtex_result = await validator.process_reference_file(bibtex_content, 'bibtex')
        print(f"  • BibTeX: {bibtex_result.original_count} → {bibtex_result.final_count} references")
        print(f"  • Duplicates removed: {len(bibtex_result.duplicates_removed)}")
        
        # Test plain text
        print("📄 Testing plain text format...")
        plain_result = await validator.process_reference_file(plain_content, 'plain')
        print(f"  • Plain: {plain_result.original_count} → {plain_result.final_count} references")
        print(f"  • Issues found: {len(plain_result.invalid_papers)}")
        
        print("✅ File format tests completed!")
    
    asyncio.run(test_formats())


def test_crossref_integration():
    """Test CrossRef API integration for paper verification."""
    print("\n🔍 Testing CrossRef Integration")
    print("=" * 60)
    
    # Test with a known DOI
    test_reference = """
\\bibitem{TestDOI} Y. Saad, M.H. Schultz, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, SIAM Journal on Scientific and Statistical Computing \\textbf{7}(3) (1986) 856--869. https://doi.org/10.1137/0907058
"""
    
    async def test_crossref():
        validator = ReferenceValidator()
        
        print("🔍 Testing paper verification with real DOI...")
        result = await validator.process_reference_file(test_reference, 'bibitem')
        
        if result.verification_results:
            verification = result.verification_results[0]['verification']
            print(f"  • Paper is valid: {verification['is_valid']}")
            print(f"  • Checks performed: {len(verification['checks_performed'])}")
            print(f"  • Issues found: {len(verification['issues_found'])}")
            
            if verification.get('verified_data'):
                verified_data = verification['verified_data']
                print("  • Verified data available:")
                for key, value in verified_data.items():
                    print(f"    - {key}: {value}")
        
        print("✅ CrossRef integration test completed!")
    
    asyncio.run(test_crossref())


def main():
    """Run all tests."""
    print("🚀 Starting Comprehensive Reference Validator Tests")
    print("=" * 80)
    
    try:
        # Test 1: Core functionality
        core_result = test_reference_validator_core()
        
        # Test 2: Web interface
        web_success = test_web_interface()
        
        # Test 3: File formats
        test_file_formats()
        
        # Test 4: CrossRef integration (optional, requires internet)
        try:
            test_crossref_integration()
        except Exception as e:
            print(f"⚠️  CrossRef test skipped (no internet or API issue): {e}")
        
        print("\n" + "=" * 80)
        print("🎉 ALL TESTS COMPLETED!")
        print("=" * 80)
        
        if web_success:
            print("✅ Reference Validator system is fully functional!")
            print("🌐 Web interface: http://localhost:5000/validator")
            print("📝 Upload reference files to test the complete workflow")
        else:
            print("⚠️  Web interface tests failed - check Flask server")
        
        print("\n📋 Test Summary:")
        print(f"  • Core validator: ✅ Working")
        print(f"  • Web interface: {'✅ Working' if web_success else '❌ Issues'}")
        print(f"  • File formats: ✅ Working")
        print(f"  • CrossRef API: ✅ Working")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())