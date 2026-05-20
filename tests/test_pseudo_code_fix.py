#!/usr/bin/env python3
"""Test the corrected pseudo code generation."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.agents.reference_validator import ReferenceValidator

def test_pseudo_code_generation():
    """Test the pseudo code generation with the correct logic."""
    print("🧪 Testing Corrected Pseudo Code Generation")
    print("=" * 60)
    
    validator = ReferenceValidator()
    
    # Test cases
    test_cases = [
        {
            'authors': 'S. Zafar, A. Rafiq, M. Sindhu',
            'year': 2020,
            'expected': 'ZaRaSi20',
            'description': '3 authors: Zafar, Rafiq, Sindhu'
        },
        {
            'authors': 'Y. Saad, M.H. Schultz',
            'year': 1986,
            'expected': 'SaSc86',
            'description': '2 authors: Saad, Schultz'
        },
        {
            'authors': 'John Smith',
            'year': 2021,
            'expected': 'Sm21',
            'description': '1 author: Smith'
        },
        {
            'authors': 'A. Einstein, B. Podolsky, N. Rosen',
            'year': 1935,
            'expected': 'EiPoRo35',
            'description': '3 authors: Einstein, Podolsky, Rosen'
        },
        {
            'authors': 'M. Ahsan, Z. Zahid, S. Ren, Extra Author',
            'year': 2021,
            'expected': 'AhZaRe21',
            'description': '4 authors (take first 3): Ahsan, Zahid, Ren'
        }
    ]
    
    print("Testing pseudo code generation:")
    print()
    
    all_correct = True
    for i, test_case in enumerate(test_cases, 1):
        result = validator._generate_correct_bibitem_key(test_case['authors'], test_case['year'])
        expected = test_case['expected']
        is_correct = result == expected
        
        status = "✅" if is_correct else "❌"
        print(f"{i}. {test_case['description']}")
        print(f"   Authors: {test_case['authors']}")
        print(f"   Expected: {expected}")
        print(f"   Got: {result}")
        print(f"   Status: {status}")
        print()
        
        if not is_correct:
            all_correct = False
    
    if all_correct:
        print("🎉 All pseudo code generation tests passed!")
    else:
        print("❌ Some tests failed!")
    
    return all_correct

def test_with_real_validation():
    """Test with actual validation process."""
    print("\n🔍 Testing with Real Validation Process")
    print("=" * 60)
    
    test_references = r"""
\bibitem{WrongKey1} S. Zafar, A. Rafiq, M. Sindhu, Computing the edge metric dimension, Journal of Mathematics \textbf{25}(3) (2020) 123--145.

\bibitem{WrongKey2} Y. Saad, M.H. Schultz, GMRES algorithm, SIAM Journal \textbf{7}(3) (1986) 856--869.

\bibitem{WrongKey3} John Smith, Some paper, Some Journal \textbf{1}(1) (2021) 1--10.
"""
    
    import asyncio
    
    async def run_validation_test():
        validator = ReferenceValidator()
        
        print("📝 Processing references with wrong keys...")
        result = await validator.process_reference_file(test_references, 'bibitem')
        
        print(f"\n📊 Results:")
        print(f"References processed: {len(result.corrected_references)}")
        
        print(f"\n🔑 Bibitem Key Corrections:")
        for ref in result.corrected_references:
            print(f"  • Key: {ref.get('key', 'unknown')}")
            print(f"    Authors: {ref.get('authors', 'unknown')}")
            print()
        
        # Check format corrections for key changes
        print(f"🔧 Format Corrections:")
        for correction in result.format_corrections:
            print(f"  • {correction['reference_key']}: {len(correction['corrections'])} corrections")
            for corr in correction['corrections']:
                if 'Bibitem Key' in corr:
                    print(f"    - {corr}")
        
        print("✅ Real validation test completed!")
    
    asyncio.run(run_validation_test())

def main():
    """Run all tests."""
    print("🚀 Testing Corrected Pseudo Code Generation")
    print("=" * 80)
    
    try:
        # Test 1: Direct pseudo code generation
        success1 = test_pseudo_code_generation()
        
        # Test 2: Real validation process
        test_with_real_validation()
        
        print("\n" + "=" * 80)
        if success1:
            print("🎉 ALL PSEUDO CODE TESTS PASSED!")
            print("✅ Pseudo code now generates correctly: ZaRaSi20, SaSc86, etc.")
        else:
            print("❌ Some tests failed - need to fix implementation")
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())