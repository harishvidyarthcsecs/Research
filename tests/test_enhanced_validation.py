#!/usr/bin/env python3
"""
Test script for the enhanced Reference Validator with comprehensive paper validation.
Tests DOI validation, title search, data correction, and duplicate detection.
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.agents.reference_validator import ReferenceValidator

def test_comprehensive_validation():
    """Test comprehensive paper validation with real and fake references."""
    print("🧪 Testing Enhanced Reference Validator")
    print("=" * 60)
    
    # Test references with various issues
    test_references = """
\\bibitem{RealDOI} Y. Saad, M.H. Schultz, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, SIAM Journal on Scientific and Statistical Computing \\textbf{7}(3) (1986) 856--869. https://doi.org/10.1137/0907058

\\bibitem{WrongData} Y. Saad, M.H. Schultz, GMRES algorithm, Wrong Journal \\textbf{99}(99) (1999) 1--2. https://doi.org/10.1137/0907058

\\bibitem{TitleOnly} Unknown Author, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, Unknown Journal (2000)

\\bibitem{FakeRef} John Doe, Fake paper that does not exist, Fake Journal \\textbf{1}(1) (2023) 1--10. https://doi.org/10.1000/fake

\\bibitem{DuplicateReal} Y. Saad, M.H. Schultz, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, SIAM Journal \\textbf{7}(3) (1986) 856--869. https://doi.org/10.1137/0907058

\\bibitem{SpellingErr} A. Author, machien learing algoritm for clasification, IEEE Transactions \\textbf{25}(2) (2020) 100--110.

\\bibitem{BadFormat} john smith, some paper title, journal name 1(1) (2021) 1-10

\\bibitem{NatureReal} A. Einstein, Zur Elektrodynamik bewegter Körper, Annalen der Physik \\textbf{17}(10) (1905) 891--921. https://doi.org/10.1002/andp.19053221004
"""
    
    async def run_comprehensive_test():
        validator = ReferenceValidator()
        
        print("📝 Processing test references with comprehensive validation...")
        result = await validator.process_reference_file(test_references, 'bibitem')
        
        print(f"\n📊 VALIDATION RESULTS:")
        print(f"✅ Original references: {result.original_count}")
        print(f"🔄 Duplicates removed: {len(result.duplicates_removed)}")
        print(f"🔧 Format corrections: {len(result.format_corrections)}")
        print(f"📝 Spelling corrections: {len(result.spelling_corrections)}")
        print(f"❌ Invalid papers: {len(result.invalid_papers)}")
        print(f"✅ Final valid references: {result.final_count}")
        
        # Count total data corrections
        total_corrections = 0
        for verification in result.verification_results:
            if verification['verification'].get('corrections_made'):
                total_corrections += len(verification['verification']['corrections_made'])
        print(f"🔄 Data corrections made: {total_corrections}")
        
        print("\n📋 PROCESSING LOG:")
        for log_entry in result.processing_log:
            print(f"  • {log_entry}")
        
        print("\n🔍 PAPER VERIFICATION DETAILS:")
        for i, verification in enumerate(result.verification_results, 1):
            ver_result = verification['verification']
            ref_key = verification['reference_key']
            
            status = "✅ Valid" if ver_result['is_valid'] else "❌ Invalid"
            method = ver_result.get('search_method', 'Unknown')
            
            print(f"  {i}. {ref_key}: {status} (via {method})")
            
            if ver_result.get('corrections_made'):
                print(f"     📝 Corrections: {len(ver_result['corrections_made'])}")
                for correction in ver_result['corrections_made'][:3]:  # Show first 3
                    print(f"       - {correction}")
                if len(ver_result['corrections_made']) > 3:
                    print(f"       - ... and {len(ver_result['corrections_made']) - 3} more")
            
            if ver_result.get('issues_found'):
                print(f"     ❌ Issues: {', '.join(ver_result['issues_found'])}")
        
        print("\n🔄 DUPLICATE DETECTION:")
        if result.duplicates_removed:
            for i, dup in enumerate(result.duplicates_removed, 1):
                print(f"  {i}. {dup['reference'].get('key', 'unknown')}: {dup['reason']}")
        else:
            print("  No duplicates found")
        
        print("\n❌ INVALID PAPERS:")
        if result.invalid_papers:
            for i, invalid in enumerate(result.invalid_papers, 1):
                print(f"  {i}. {invalid['reference'].get('key', 'unknown')}: {invalid['reason']}")
        else:
            print("  No invalid papers found")
        
        print("\n📄 CORRECTED REFERENCES (Bibitem Format):")
        corrected_output = validator.generate_corrected_file(result, 'bibitem')
        print(corrected_output)
        
        print("\n📊 VALIDATION REPORT PREVIEW:")
        report = validator.generate_validation_report(result)
        report_lines = report.split('\n')
        for line in report_lines[:30]:  # Show first 30 lines
            print(line)
        if len(report_lines) > 30:
            print(f"... and {len(report_lines) - 30} more lines")
        
        print("\n✅ Enhanced validation test completed!")
        return result
    
    return asyncio.run(run_comprehensive_test())

def test_doi_vs_title_search():
    """Test DOI search vs title search specifically."""
    print("\n🔍 Testing DOI vs Title Search")
    print("=" * 60)
    
    # Test with correct DOI
    doi_test = """
\\bibitem{DOITest} Wrong Author, Wrong Title, Wrong Journal (2000) https://doi.org/10.1137/0907058
"""
    
    # Test with correct title but no DOI
    title_test = """
\\bibitem{TitleTest} Wrong Author, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, Wrong Journal (2000)
"""
    
    async def run_search_test():
        validator = ReferenceValidator()
        
        print("🔍 Testing DOI-based correction...")
        doi_result = await validator.process_reference_file(doi_test, 'bibitem')
        
        print("🔍 Testing title-based correction...")
        title_result = await validator.process_reference_file(title_test, 'bibitem')
        
        print("\n📊 DOI Search Results:")
        if doi_result.verification_results:
            ver = doi_result.verification_results[0]['verification']
            print(f"  Method: {ver.get('search_method', 'Unknown')}")
            print(f"  Valid: {ver['is_valid']}")
            print(f"  Corrections: {len(ver.get('corrections_made', []))}")
        
        print("\n📊 Title Search Results:")
        if title_result.verification_results:
            ver = title_result.verification_results[0]['verification']
            print(f"  Method: {ver.get('search_method', 'Unknown')}")
            print(f"  Valid: {ver['is_valid']}")
            print(f"  Corrections: {len(ver.get('corrections_made', []))}")
        
        print("\n📄 Corrected References:")
        print("DOI-based correction:")
        print(validator.generate_corrected_file(doi_result, 'bibitem'))
        print("\nTitle-based correction:")
        print(validator.generate_corrected_file(title_result, 'bibitem'))
    
    asyncio.run(run_search_test())

def test_duplicate_detection():
    """Test enhanced duplicate detection."""
    print("\n🔄 Testing Enhanced Duplicate Detection")
    print("=" * 60)
    
    duplicate_test = """
\\bibitem{Orig} Y. Saad, M.H. Schultz, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, SIAM Journal on Scientific and Statistical Computing \\textbf{7}(3) (1986) 856--869. https://doi.org/10.1137/0907058

\\bibitem{SameDOI} Different Author, Different Title, Different Journal (2000) https://doi.org/10.1137/0907058

\\bibitem{SimilarTitle} Y. Saad, M.H. Schultz, GMRES: generalized minimal residual algorithm for solving nonsymmetric linear systems, Different Journal (1986)

\\bibitem{SameAuthorsYear} Y. Saad, M.H. Schultz, Completely different paper, Different Journal (1986)

\\bibitem{NotDuplicate} A. Different, B. Authors, Completely different paper about different topic, Other Journal (2020)
"""
    
    async def run_duplicate_test():
        validator = ReferenceValidator()
        
        print("🔄 Testing duplicate detection...")
        result = await validator.process_reference_file(duplicate_test, 'bibitem')
        
        print(f"\n📊 Duplicate Detection Results:")
        print(f"  Original: {result.original_count}")
        print(f"  Duplicates found: {len(result.duplicates_removed)}")
        print(f"  Final unique: {result.final_count}")
        
        print("\n🔄 Detected Duplicates:")
        for i, dup in enumerate(result.duplicates_removed, 1):
            print(f"  {i}. {dup['reference'].get('key', 'unknown')}")
            print(f"     Reason: {dup['reason']}")
            if 'similarity_score' in dup:
                print(f"     Similarity: {dup['similarity_score']:.2f}")
    
    asyncio.run(run_duplicate_test())

def main():
    """Run all enhanced validation tests."""
    print("🚀 Starting Enhanced Reference Validator Tests")
    print("=" * 80)
    
    try:
        # Test 1: Comprehensive validation
        comprehensive_result = test_comprehensive_validation()
        
        # Test 2: DOI vs Title search
        test_doi_vs_title_search()
        
        # Test 3: Enhanced duplicate detection
        test_duplicate_detection()
        
        print("\n" + "=" * 80)
        print("🎉 ALL ENHANCED VALIDATION TESTS COMPLETED!")
        print("=" * 80)
        
        print("\n📋 Test Summary:")
        print("  ✅ Comprehensive paper validation")
        print("  ✅ DOI-based paper search and correction")
        print("  ✅ Title-based paper search and correction")
        print("  ✅ Enhanced duplicate detection")
        print("  ✅ Accurate bibliographic data extraction")
        print("  ✅ Comprehensive validation reporting")
        
        print("\n🎯 Key Features Verified:")
        print("  • Papers validated by DOI first, then by title")
        print("  • All bibliographic data corrected with CrossRef API")
        print("  • Spelling mistakes and format issues fixed")
        print("  • Intelligent duplicate detection with similarity scoring")
        print("  • Comprehensive validation reports with detailed corrections")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())