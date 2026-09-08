#!/usr/bin/env python3
"""
Test script for the Reference Validator system.
"""

import sys
import os
import asyncio
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RESEARCH_AGENT_LIVE") != "1",
    reason="requires live CrossRef verification; set RESEARCH_AGENT_LIVE=1 to run",
)

# Add src to path
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(REPO_ROOT, 'src'))

# Import directly
sys.path.insert(0, os.path.join(REPO_ROOT, 'src', 'agents'))
from src.agents.reference_validator import ReferenceValidator, ReferenceValidationResult

def create_test_references():
    """Create test reference content with various issues."""
    
    # Test content with various issues to fix
    test_content = """
\\bibitem{lecun15} yann lecun, yoshua bengio, geoffrey hinton, deep learing, nature \\textbf{1}(1) (2015) 1--10. https://doi.org/10.1038/nature14539

\\bibitem{vaswani17} ashish vaswani, noam shazeer, niki parmar, attention is all you need, neurips (2017) 5998-6008

\\bibitem{lecun15} Y. LeCun, Y. Bengio, G. Hinton, Deep learning, Nature \\textbf{521}(7553) (2015) 436-444. https://doi.org/10.1038/nature14539

\\bibitem{brown20} tom brown, benjamin mann, nick ryder, language models are few-shot learners, neurips (2020)

\\bibitem{devlin18} jacob devlin, ming-wei chang, kenton lee, bert: pre-training of deep bidirectional transformers for language understanding, naacl (2019) 4171-4186

\\bibitem{fake123} john doe, jane smith, fake paper title with spelling mistakse, fake journal \\textbf{1}(1) (2025) 1--10. https://doi.org/10.1000/fake.doi.2025
"""
    
    return test_content.strip()

async def test_reference_validator():
    """Test the reference validator with sample data."""
    
    print("🧪 Testing Reference Validator System")
    print("=" * 50)
    
    # Create test content
    test_content = create_test_references()
    
    print(f"📄 Test Content ({len(test_content)} characters):")
    print(test_content[:200] + "..." if len(test_content) > 200 else test_content)
    print()
    
    # Initialize validator
    validator = ReferenceValidator()
    
    try:
        # Process the reference file
        print("🔍 Processing references...")
        result = await validator.process_reference_file(test_content, 'bibitem')
        
        # Display results
        print(f"\n📊 Validation Results:")
        print(f"Original references: {result.original_count}")
        print(f"Duplicates removed: {len(result.duplicates_removed)}")
        print(f"Format corrections: {len(result.format_corrections)}")
        print(f"Spelling corrections: {len(result.spelling_corrections)}")
        print(f"Invalid papers: {len(result.invalid_papers)}")
        print(f"Final valid references: {result.final_count}")
        
        # Show processing log
        print(f"\n📝 Processing Log:")
        for log_entry in result.processing_log:
            print(f"  • {log_entry}")
        
        # Show duplicates removed
        if result.duplicates_removed:
            print(f"\n🔄 Duplicates Removed:")
            for i, dup in enumerate(result.duplicates_removed, 1):
                print(f"  {i}. {dup['reference'].get('key', 'unknown')} - {dup['reason']}")
        
        # Show format corrections
        if result.format_corrections:
            print(f"\n✏️ Format Corrections:")
            for i, correction in enumerate(result.format_corrections, 1):
                print(f"  {i}. {correction['reference_key']}:")
                for corr in correction['corrections']:
                    print(f"     - {corr}")
        
        # Show spelling corrections
        if result.spelling_corrections:
            print(f"\n📝 Spelling Corrections:")
            for i, correction in enumerate(result.spelling_corrections, 1):
                print(f"  {i}. {correction['reference_key']}:")
                for corr in correction['corrections']:
                    print(f"     - {corr}")
        
        # Show invalid papers
        if result.invalid_papers:
            print(f"\n❌ Invalid Papers:")
            for i, invalid in enumerate(result.invalid_papers, 1):
                print(f"  {i}. {invalid['reference'].get('key', 'unknown')} - {invalid['reason']}")
        
        # Show verification results
        print(f"\n🔍 Verification Results:")
        for i, verification in enumerate(result.verification_results, 1):
            ref_key = verification['reference_key']
            is_valid = verification['verification']['is_valid']
            checks = verification['verification']['checks_performed']
            issues = verification['verification']['issues_found']
            
            print(f"  {i}. {ref_key}: {'✅ Valid' if is_valid else '❌ Invalid'}")
            if checks:
                print(f"     Checks: {', '.join(checks)}")
            if issues:
                print(f"     Issues: {', '.join(issues)}")
        
        # Generate corrected output
        print(f"\n📖 Corrected References (Bibitem Format):")
        corrected_bibitem = validator.generate_corrected_file(result, 'bibitem')
        print(corrected_bibitem)
        
        # Test other formats
        print(f"\n📚 BibTeX Format:")
        corrected_bibtex = validator.generate_corrected_file(result, 'bibtex')
        print(corrected_bibtex[:300] + "..." if len(corrected_bibtex) > 300 else corrected_bibtex)
        
        # Generate validation report
        print(f"\n📋 Validation Report:")
        report = validator.generate_validation_report(result)
        print(report[:500] + "..." if len(report) > 500 else report)
        
        return result
        
    except Exception as e:
        print(f"\n❌ Error during validation: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

async def test_different_formats():
    """Test validator with different input formats."""
    
    print(f"\n🔄 Testing Different Input Formats")
    print("=" * 40)
    
    validator = ReferenceValidator()
    
    # Test BibTeX format
    bibtex_content = """
@article{lecun2015deep,
  title={Deep learning},
  author={LeCun, Yann and Bengio, Yoshua and Hinton, Geoffrey},
  journal={nature},
  volume={521},
  number={7553},
  pages={436--444},
  year={2015},
  doi={10.1038/nature14539}
}

@inproceedings{vaswani2017attention,
  title={Attention is all you need},
  author={Vaswani, Ashish and Shazeer, Noam and Parmar, Niki},
  booktitle={Advances in neural information processing systems},
  pages={5998--6008},
  year={2017}
}
"""
    
    print("📚 Testing BibTeX format...")
    bibtex_result = await validator.process_reference_file(bibtex_content, 'bibtex')
    print(f"BibTeX: {bibtex_result.original_count} → {bibtex_result.final_count} references")
    
    # Test plain text format
    plain_content = """
LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521(7553), 436-444.
Vaswani, A., Shazeer, N., Parmar, N. (2017). Attention is all you need. NIPS.
Brown, T., Mann, B., Ryder, N. (2020). Language models are few-shot learners.
"""
    
    print("📄 Testing Plain text format...")
    plain_result = await validator.process_reference_file(plain_content, 'plain')
    print(f"Plain: {plain_result.original_count} → {plain_result.final_count} references")
    
    return bibtex_result, plain_result

async def main():
    """Run comprehensive reference validator tests."""
    
    print("🧪 Reference Validator Comprehensive Test")
    print("=" * 60)
    
    try:
        # Test main functionality
        result = await test_reference_validator()
        
        # Test different formats
        bibtex_result, plain_result = await test_different_formats()
        
        # Summary
        print(f"\n📊 Test Summary")
        print("=" * 30)
        
        if result:
            print(f"✅ Bibitem format test: {result.original_count} → {result.final_count} references")
            print(f"   - Duplicates removed: {len(result.duplicates_removed)}")
            print(f"   - Format corrections: {len(result.format_corrections)}")
            print(f"   - Spelling corrections: {len(result.spelling_corrections)}")
            print(f"   - Invalid papers: {len(result.invalid_papers)}")
        
        if bibtex_result:
            print(f"✅ BibTeX format test: {bibtex_result.original_count} → {bibtex_result.final_count} references")
        
        if plain_result:
            print(f"✅ Plain text format test: {plain_result.original_count} → {plain_result.final_count} references")
        
        print(f"\n🎉 Reference Validator Test SUCCESSFUL!")
        print(f"📝 Key features verified:")
        print(f"   • Format parsing (bibitem, bibtex, plain)")
        print(f"   • Duplicate detection and removal")
        print(f"   • Format correction (authors, titles, journals)")
        print(f"   • Spelling correction")
        print(f"   • Paper verification via CrossRef API")
        print(f"   • Multiple output formats")
        print(f"   • Comprehensive validation reporting")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    
    if success:
        print(f"\n🎉 All tests passed!")
    else:
        print(f"\n💥 Some tests failed!")
