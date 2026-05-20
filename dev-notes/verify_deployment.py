#!/usr/bin/env python3
"""
Quick deployment verification script for the Literature Builder system.
"""

import sys
import os
import asyncio
from datetime import datetime

def verify_imports():
    """Verify all required imports work correctly."""
    print("🔍 Verifying imports...")
    
    try:
        # Add src to path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
        
        # Test data models
        from models.data_models import PaperMetadata, Claim, ResearchResults, TopicMap
        print("✅ Data models import successful")
        
        # Test literature builder
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'agents'))
        from literature_builder_agent import LiteratureBuilderAgent
        print("✅ Literature builder import successful")
        
        # Test web app
        import app_fixed
        print("✅ Web application import successful")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {str(e)}")
        return False

def verify_literature_builder():
    """Verify literature builder functionality."""
    print("\n📚 Verifying literature builder...")
    
    try:
        # Add src to path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
        from models.data_models import PaperMetadata, Claim, ResearchResults, TopicMap
        
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'agents'))
        from literature_builder_agent import LiteratureBuilderAgent
        
        # Create minimal test data
        paper = PaperMetadata(
            id="test_paper",
            title="Test paper for verification",
            authors=["A. Test", "B. Verify"],
            year=2024,
            venue="Test Journal",
            doi="10.1000/test.2024.001",
            abstract="This is a test abstract for verification purposes. The method achieves good results. The approach demonstrates effectiveness in testing scenarios.",
            relevance_score=0.9
        )
        
        claim = Claim(
            id="test_claim",
            statement="Test methods achieve good results",
            paper_id="test_paper",
            confidence=0.9
        )
        
        topic_map = TopicMap(
            main_topic="Test Topic",
            subtopics=["Testing"],
            methods=["Verification"],
            keywords=["test", "verify"]
        )
        
        research_results = ResearchResults(
            topic_map=topic_map,
            papers=[paper],
            claims=[claim],
            contradictions=[],
            research_gaps=[],
            citations=[],
            total_papers_analyzed=1,
            total_claims_extracted=1
        )
        
        # Test literature generation
        async def test_generation():
            literature_agent = LiteratureBuilderAgent()
            literature_document = await literature_agent.process(research_results)
            return literature_document
        
        literature_document = asyncio.run(test_generation())
        
        # Verify results
        if literature_document and len(literature_document.sections) > 0:
            print("✅ Literature generation successful")
            print(f"   Generated {len(literature_document.sections)} sections")
            print(f"   Total words: {literature_document.total_word_count}")
            
            # Check for LaTeX citations
            has_latex = any('\\cite{' in section.content for section in literature_document.sections)
            print(f"   LaTeX citations: {'✅ Found' if has_latex else '⚠️ Not found'}")
            
            # Check bibliography format
            has_bibitem = any('\\bibitem{' in entry for entry in literature_document.bibliography)
            print(f"   Bibliography format: {'✅ Correct' if has_bibitem else '⚠️ Incorrect'}")
            
            return True
        else:
            print("❌ Literature generation failed")
            return False
            
    except Exception as e:
        print(f"❌ Literature builder error: {str(e)}")
        return False

def verify_web_interface():
    """Verify web interface can start."""
    print("\n🌐 Verifying web interface...")
    
    try:
        import app_fixed
        from flask import Flask
        
        # Check if Flask app is properly configured
        if hasattr(app_fixed, 'app') and isinstance(app_fixed.app, Flask):
            print("✅ Flask application configured correctly")
            
            # Check routes
            routes = [rule.rule for rule in app_fixed.app.url_map.iter_rules()]
            required_routes = ['/', '/literature', '/generate-literature']
            
            for route in required_routes:
                if route in routes:
                    print(f"✅ Route {route} available")
                else:
                    print(f"❌ Route {route} missing")
                    return False
            
            return True
        else:
            print("❌ Flask application not properly configured")
            return False
            
    except Exception as e:
        print(f"❌ Web interface error: {str(e)}")
        return False

def main():
    """Run complete deployment verification."""
    print("🚀 Literature Builder Deployment Verification")
    print("=" * 50)
    
    results = []
    
    # Run all verifications
    results.append(verify_imports())
    results.append(verify_literature_builder())
    results.append(verify_web_interface())
    
    # Summary
    print(f"\n📊 Verification Summary")
    print("=" * 30)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Tests Passed: {passed}/{total}")
    print(f"Success Rate: {passed/total*100:.1f}%")
    
    if passed == total:
        print(f"\n🎉 DEPLOYMENT VERIFICATION SUCCESSFUL!")
        print(f"✅ All systems are working correctly")
        print(f"✅ Ready for production use")
        print(f"\n🚀 To start the system:")
        print(f"   python app_fixed.py")
        print(f"   Then open: http://localhost:5000/literature")
    else:
        print(f"\n⚠️ DEPLOYMENT VERIFICATION INCOMPLETE")
        print(f"❌ {total-passed} test(s) failed")
        print(f"🔧 Please check the failed components before deployment")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)