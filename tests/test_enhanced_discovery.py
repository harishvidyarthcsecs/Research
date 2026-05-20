"""
Test script for enhanced paper discovery with multiple sources.
"""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.agents.enhanced_paper_discovery_agent import EnhancedPaperDiscoveryAgent
from src.models.data_models import TopicMap
from api_config import APIConfig


async def test_enhanced_discovery():
    """Test enhanced paper discovery with multiple sources."""
    
    print("🔍 Testing Enhanced Paper Discovery")
    print("=" * 50)
    
    # Show current configuration
    print("📊 Current API Configuration:")
    enabled_sources = APIConfig.get_enabled_sources()
    for source in enabled_sources:
        print(f"  ✅ {source}")
    
    issues = APIConfig.validate_config()
    if issues:
        print("\n⚠️  Configuration Issues:")
        for issue in issues:
            print(f"  - {issue}")
    
    print(f"\n🎯 Total Sources Enabled: {len(enabled_sources)}")
    
    # Create test topic
    topic_map = TopicMap(
        main_topic="Machine Learning for Drug Discovery",
        subtopics=["molecular design", "drug screening", "QSAR"],
        methods=["neural networks", "deep learning"],
        keywords=["machine learning", "drug discovery", "molecular", "pharmaceutical"]
    )
    
    print(f"\n🔬 Testing with topic: {topic_map.main_topic}")
    
    # Test enhanced discovery
    agent = EnhancedPaperDiscoveryAgent(max_papers_per_source=20)
    
    try:
        async with agent:
            print("\n⏳ Searching multiple databases...")
            papers = await agent.process(topic_map)
            
            print(f"\n📊 RESULTS:")
            print(f"Total papers found: {len(papers)}")
            
            # Group by source
            sources = {}
            for paper in papers:
                venue = paper.venue
                if venue not in sources:
                    sources[venue] = []
                sources[venue].append(paper)
            
            print(f"\n📚 Papers by Source:")
            for source, source_papers in sources.items():
                print(f"  {source}: {len(source_papers)} papers")
            
            # Show top papers
            print(f"\n🏆 Top 5 Papers:")
            for i, paper in enumerate(papers[:5], 1):
                print(f"{i}. {paper.title}")
                print(f"   Authors: {', '.join(paper.authors[:3])}")
                print(f"   Year: {paper.year}, Venue: {paper.venue}")
                print(f"   Relevance: {paper.relevance_score:.2f}")
                if paper.doi:
                    print(f"   DOI: {paper.doi}")
                print()
            
            # Show API status
            api_status = agent.get_api_status()
            print(f"🔧 API Status:")
            for api_name, status in api_status.items():
                status_icon = "✅" if status["ready"] else "❌"
                print(f"  {status_icon} {api_name.title()}: {'Ready' if status['ready'] else 'Not configured'}")
    
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


async def test_specific_apis():
    """Test specific APIs individually."""
    
    print("\n🧪 Testing Individual APIs")
    print("=" * 30)
    
    topic_map = TopicMap(
        main_topic="Graph Neural Networks",
        keywords=["graph", "neural", "networks"]
    )
    
    agent = EnhancedPaperDiscoveryAgent(max_papers_per_source=5)
    
    async with agent:
        # Test ArXiv
        print("📖 Testing ArXiv...")
        try:
            arxiv_papers = await agent._search_arxiv(topic_map)
            print(f"  Found {len(arxiv_papers)} papers from ArXiv")
        except Exception as e:
            print(f"  ❌ ArXiv error: {e}")
        
        # Test Semantic Scholar
        print("🧠 Testing Semantic Scholar...")
        try:
            ss_papers = await agent._search_semantic_scholar(topic_map)
            print(f"  Found {len(ss_papers)} papers from Semantic Scholar")
        except Exception as e:
            print(f"  ❌ Semantic Scholar error: {e}")
        
        # Test CrossRef
        print("🔗 Testing CrossRef...")
        try:
            cr_papers = await agent._search_crossref(topic_map)
            print(f"  Found {len(cr_papers)} papers from CrossRef")
        except Exception as e:
            print(f"  ❌ CrossRef error: {e}")


if __name__ == "__main__":
    print("🚀 Enhanced Paper Discovery Test")
    print("This will test searching multiple academic databases")
    print()
    
    # Run tests
    asyncio.run(test_enhanced_discovery())
    asyncio.run(test_specific_apis())
    
    print("\n💡 To enable more sources:")
    print("1. Run: python api_config.py")
    print("2. Get API keys from publisher websites")
    print("3. Set environment variables")
    print("4. Update api_config.py to enable APIs")