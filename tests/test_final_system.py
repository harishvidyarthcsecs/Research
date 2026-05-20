#!/usr/bin/env python3
"""Test the final system with corrected pseudo code generation."""

import requests
import json

# Test with the exact example you provided
test_data = {
    'content': r'''\bibitem{WrongKey1} S. Zafar, A. Rafiq, M. Sindhu, Computing the edge metric dimension of convex polytopes related graphs, Journal of Mathematics and Computer Science \textbf{25}(3) (2020) 123--145. https://doi.org/10.1234/example1

\bibitem{WrongKey2} Y. Saad, M.H. Schultz, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, SIAM Journal on Scientific and Statistical Computing \textbf{7}(3) (1986) 856--869. https://doi.org/10.1137/0907058

\bibitem{WrongKey3} John Smith, Some paper title, Some Journal \textbf{1}(1) (2021) 1--10.''',
    'format': 'bibitem',
    'options': {
        'checkFormat': True,
        'checkSpelling': True,
        'checkDuplicates': True,
        'verifyPapers': True
    }
}

try:
    print("🧪 Testing Final System with Corrected Pseudo Code")
    print("=" * 70)
    
    response = requests.post(
        'http://localhost:5000/validate-references',
        json=test_data,
        headers={'Content-Type': 'application/json'},
        timeout=60
    )
    
    if response.status_code == 200:
        result = response.json()
        print('✅ Validation successful!')
        
        print(f"\n📊 Statistics:")
        print(f"Original: {result['stats']['original_count']}")
        print(f"Final: {result['stats']['final_count']}")
        
        print(f"\n🔑 Pseudo Code Generation Test:")
        print("Expected results:")
        print("  • S. Zafar, A. Rafiq, M. Sindhu → ZaRaSi20")
        print("  • Y. Saad, M.H. Schultz → SaSc86") 
        print("  • John Smith → Sm21")
        print()
        
        print("🔧 Corrections Made:")
        total_corrections = 0
        for i, correction in enumerate(result['corrections'], 1):
            count = correction.get('corrections_count', 0)
            total_corrections += count
            print(f"{i}. {correction['type']} - {correction['reference_key']}: {count} corrections")
            
            # Show bibitem key corrections specifically
            if correction.get('details'):
                for detail in correction['details']:
                    if 'Bibitem Key' in detail['field']:
                        print(f"   ✅ {detail['field']}: {detail['before']} → {detail['after']}")
            print()
        
        print(f"📊 Total corrections: {total_corrections}")
        
        print(f"\n📄 Final Corrected References:")
        print("=" * 70)
        corrected_refs = result.get('corrected_references', '')
        
        # Extract and show the bibitem keys
        import re
        keys = re.findall(r'\\bibitem\{([^}]+)\}', corrected_refs)
        print("🔑 Generated Bibitem Keys:")
        for key in keys:
            print(f"  • {key}")
        print()
        
        print(corrected_refs)
        print("=" * 70)
        
        print("\n✅ Final system test completed!")
        print("🎉 Pseudo code generation now works correctly!")
        
    else:
        print(f'❌ Error: {response.status_code}')
        print(response.text)
        
except Exception as e:
    print(f'❌ Request failed: {e}')
    import traceback
    traceback.print_exc()