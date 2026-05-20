"""
Test the corrected author formatting.
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.agents.custom_citation_formatter import CustomCitationFormatter


def test_author_formatting():
    """Test the corrected author formatting."""
    
    print("👥 Testing Corrected Author Formatting")
    print("=" * 50)
    
    formatter = CustomCitationFormatter()
    
    # Test cases
    test_authors = [
        ["Y. Saad", "M.H. Schultz"],
        ["Ivan Gutman"],
        ["David K. Duvenaud", "Dougal Maclaurin", "Jorge Iparraguirre"],
        ["Thomas N. Kipf", "Max Welling"],
        ["John Smith", "Jane A. Doe", "Robert B. Johnson"]
    ]
    
    print("Expected Format: 'Y. Saad, M.H. Schultz' (initials first)")
    print("-" * 50)
    
    for authors in test_authors:
        formatted = formatter._format_authors_custom(authors)
        print(f"Input:  {authors}")
        print(f"Output: {formatted}")
        print()
    
    # Test individual author formatting
    print("🔍 Individual Author Formatting:")
    print("-" * 30)
    
    individual_tests = [
        "Y. Saad",
        "M.H. Schultz", 
        "David K. Duvenaud",
        "Thomas N. Kipf",
        "Ivan Gutman"
    ]
    
    for author in individual_tests:
        formatted = formatter._format_single_author(author)
        print(f"'{author}' → '{formatted}'")
    
    print(f"\n✅ Author formatting test completed!")
    print("Format should now match: Y. Saad, M.H. Schultz")


if __name__ == "__main__":
    test_author_formatting()