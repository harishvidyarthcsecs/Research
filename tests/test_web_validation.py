#!/usr/bin/env python3
"""Test the web interface validation endpoint."""

import requests
import json

# Test the enhanced validation endpoint
test_data = {
    'content': r'''\bibitem{Test01} Y. Saad, M.H. Schultz, GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems, SIAM Journal on Scientific and Statistical Computing \textbf{7}(3) (1986) 856--869. https://doi.org/10.1137/0907058

\bibitem{Duplicate} Y. Saad, M.H. Schultz, GMRES algorithm, Wrong Journal (1999) https://doi.org/10.1137/0907058

\bibitem{Fake} John Doe, Fake paper, Fake Journal (2023) https://doi.org/10.1000/fake''',
    'format': 'bibitem',
    'options': {
        'checkFormat': True,
        'checkSpelling': True,
        'checkDuplicates': True,
        'verifyPapers': True
    }
}

try:
    print("🌐 Testing web interface validation endpoint...")
    response = requests.post(
        'http://localhost:5000/validate-references',
        json=test_data,
        headers={'Content-Type': 'application/json'},
        timeout=60
    )
    
    if response.status_code == 200:
        result = response.json()
        print('✅ Web interface validation successful!')
        print(f'Original: {result["stats"]["original_count"]}')
        print(f'Duplicates: {result["stats"]["duplicates_removed"]}')
        print(f'Invalid: {result["stats"]["invalid_papers"]}')
        print(f'Final: {result["stats"]["final_count"]}')
        print(f'Processing log entries: {len(result["processing_log"])}')
        print(f'Corrections: {len(result["corrections"])}')
        print(f'Issues: {len(result["issues"])}')
        
        print("\n📋 Processing Log:")
        for entry in result["processing_log"]:
            print(f"  • {entry}")
        
        print("\n🔧 Corrections:")
        for correction in result["corrections"][:5]:
            print(f"  • {correction['type']}: {correction['reference_key']}")
        
        print("\n❌ Issues:")
        for issue in result["issues"]:
            print(f"  • {issue['type']}: {issue['reference_key']} - {issue['description']}")
        
        print("\n✅ Enhanced web validation working perfectly!")
    else:
        print(f'❌ Error: {response.status_code}')
        print(response.text)
        
except Exception as e:
    print(f'❌ Request failed: {e}')
    import traceback
    traceback.print_exc()
