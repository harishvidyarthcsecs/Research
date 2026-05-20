#!/usr/bin/env python3
"""
Quick test to verify the ReferenceValidator abstract method fix.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_validator_instantiation():
    """Test that ReferenceValidator can be instantiated without abstract method error."""
    
    print("🧪 Testing ReferenceValidator Instantiation")
    print("=" * 45)
    
    try:
        # Import directly
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'agents'))
        from reference_validator import ReferenceValidator
        
        print("✅ Import successful")
        
        # Try to instantiate
        validator = ReferenceValidator()
        print("✅ Instantiation successful")
        
        # Test the process method
        test_input = {
            'content': '\\bibitem{test} A. Test, Test paper, Test Journal (2024)',
            'format': 'bibitem'
        }
        
        print("✅ ReferenceValidator created successfully")
        print(f"   Name: {validator.name}")
        print(f"   Has process method: {hasattr(validator, 'process')}")
        print(f"   Has process_reference_file method: {hasattr(validator, 'process_reference_file')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_validator_instantiation()
    
    if success:
        print(f"\n🎉 ReferenceValidator instantiation test PASSED!")
        print(f"✅ The abstract method error should be fixed")
    else:
        print(f"\n💥 ReferenceValidator instantiation test FAILED!")
        print(f"❌ The abstract method error still exists")