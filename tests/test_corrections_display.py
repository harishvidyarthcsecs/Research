#!/usr/bin/env python3
"""Test the improved corrections display."""

import requests
import json

# Test the corrections display with sample references
test_data = {
    'content': r'''\bibitem{Test01} Y. Saad, M.H. Schultz, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, SIAM Journal on Scientific and Statistical Computing \textbf{7}(3) (1986) 856--869. https://doi.org/10.1137/0907058

\bibitem{Test02} S. Zafar, A. Rafiq, M. Sindhu, Computing the edge metric dimension, Journal of Mathematics \textbf{25}(3) (2020) 123--145. https://doi.org/10.1234/fake

\bibitem{Test03} john smith, some paper title, journal name (2021) 1-10''',
    'format': 'bibitem',
    'options': {
        'checkFormat': True,
        'checkSpelling': True,
        'checkDuplicates': True,
        'verifyPapers': True
    }
}

try:
    print("🌐 Testing improved corrections display...")
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
        
        print(f"\n🔧 Corrections Structure:")
        for i, correction in enumerate(result['corrections'], 1):
            print(f"{i}. {correction['type']} - {correction['reference_key']}")
            print(f"   Count: {correction.get('corrections_count', 0)}")
            if correction.get('details'):
                print(f"   Details: {len(correction['details'])} items")
                for detail in correction['details'][:2]:  # Show first 2
                    print(f"     - {detail['field']}: {detail['before']} → {detail['after']}")
            print()
        
        print("✅ Corrections display test completed!")
    else:
        print(f'❌ Error: {response.status_code}')
        print(response.text)
        
except Exception as e:
    print(f'❌ Request failed: {e}')
    import traceback
    traceback.print_exc()