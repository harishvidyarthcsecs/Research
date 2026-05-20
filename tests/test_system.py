"""
Simple test script to verify the research system works.
"""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.research_system import AutonomousResearchSystem


async def test_system():
    """Test the research system with a simple topic."""
    
    print("🔬 Testing Autonomous Research System")
    print("=" * 50)
    
    try:
        # Initialize system
        system = AutonomousResearchSystem()
        print("✅ System initialized successfully")
        
        # Test with a simple topic
        topic = "Graph Neural Networks for Drug Discovery"
        print(f"\n🎯 Testing with topic: {topic}")
        
        # Run research
        results = await system.research(topic)
        
        # Display results
        print(f"\n📊 RESULTS SUMMARY:")
        print(f"Topic: {results.topic_map.main_topic}")
        print(f"Subtopics found: {len(results.topic_map.subtopics)}")
        print(f"Papers discovered: {len(results.papers)}")
        print(f"Claims extracted: {len(results.claims)}")
        print(f"Contradictions found: {len(results.contradictions)}")
        print(f"Research gaps identified: {len(results.research_gaps)}")
        print(f"Citations generated: {len(results.citations)}")
        
        # Show some examples
        if results.topic_map.subtopics:
            print(f"\nExample subtopics: {results.topic_map.subtopics[:3]}")
        
        if results.papers:
            print(f"\nExample paper: {results.papers[0].title}")
        
        if results.claims:
            print(f"\nExample claim: {results.claims[0].statement[:100]}...")
        
        if results.research_gaps:
            print(f"\nExample research gap: {results.research_gaps[0].description}")
        
        print("\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_system())