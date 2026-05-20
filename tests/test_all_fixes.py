#!/usr/bin/env python3
"""Test all the fixes implemented."""

import requests
import json

# Test all the fixes with problematic references
test_data = {
    'content': r'''\bibitem{PrArJa25} S. Zafar, A. Rafiq, M. Sindhu, Computing the edge metric dimension of convex polytopes related graphs, Journal of Mathematics and Computer Science \textbf{25}(3) (2020) 123--145. https://doi.org/10.1234/example1

\bibitem{WrongKey} M. Ahsan, Z. Zahid, S. Ren, Fault-tolerant edge metric dimension of certain families of graphs, AIMS Mathematics \textbf{6}(8) (2021) 8334--8354. https://doi.org/10.3934/math.2021484

\bibitem{TestValid} Y. Saad, M.H. Schultz, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, SIAM Journal on Scientific and Statistical Computing \textbf{7}(3) (1986) 856--869. https://doi.org/10.1137/0907058''',
    'format': 'bibitem',
    'options': {
        'checkFormat': True,
        'checkSpelling': True,
        'checkDuplicates': True,
        'verifyPapers': True
    }
}

try:
    print("🧪 Testing All Fixes...")
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
        
        print(f"\n🔧 Corrections Summary:")
        total_corrections = 0
        for i, correction in enumerate(result['corrections'], 1):
            count = correction.get('corrections_count', 0)
            total_corrections += count
            print(f"{i}. {correction['type']} - {correction['reference_key']}: {count} corrections")
            
            # Show first few details
            if correction.get('details'):
                for detail in correction['details'][:3]:  # Show first 3
                    print(f"   - {detail['field']}: {detail['before']} → {detail['after']}")
                if len(correction['details']) > 3:
                    print(f"   - ... and {len(correction['details']) - 3} more")
            print()
        
        print(f"📊 Total corrections made: {total_corrections}")
        
        print(f"\n📄 Corrected References:")
        print("=" * 80)
        print(result.get('corrected_references', 'No corrected references'))
        print("=" * 80)
        
        print("\n✅ All fixes test completed!")
        
        # Test corrections details page
        print("\n🌐 Testing corrections details page...")
        corrections_data = json.dumps(result['corrections'])
        print(f"Corrections data size: {len(corrections_data)} characters")
        print("✅ Corrections data ready for details page")
        
    else:
        print(f'❌ Error: {response.status_code}')
        print(response.text)
        
except Exception as e:
    print(f'❌ Request failed: {e}')
    import traceback
    traceback.print_exc()