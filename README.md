# Autonomous Research Agent System

A multi-agent research system that autonomously performs academic and technical research end-to-end with minimal user intervention, producing structured, verifiable, and reference-backed outputs.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/mohamedaaris/Research/actions/workflows/ci.yml/badge.svg)](https://github.com/mohamedaaris/Research/actions)

## System Architecture

The system consists of 8 specialized agents working in a coordinated pipeline:

1. **Topic Expansion Agent** - Decomposes topics into subtopics and research directions
2. **Paper Discovery Agent** - Searches and retrieves relevant academic papers from ArXiv and other sources
3. **Paper Reading & Claim Extraction Agent** - Extracts structured claims from papers using pattern matching
4. **Claim Normalization & Verification Agent** - Normalizes and validates claims for consistency
5. **Contradiction Detection Agent** - Identifies contradictions and agreements between claims
6. **Research Gap Detection Agent** - Identifies unexplored research areas and methodological gaps
7. **Citation & Reference Builder Agent** - Generates citations in multiple formats (BibTeX, APA, IEEE, MLA)
8. **Long-Term Memory Agent** - Maintains persistent knowledge graph and caching

## Features

- **Autonomous Research Pipeline**: Complete end-to-end research with minimal user input
- **Multi-Source Paper Discovery**: Searches ArXiv, Semantic Scholar, CrossRef, and PubMed
- **Structured Claim Extraction**: Uses LLM-based extraction for quantitative and qualitative claims
- **AI Writing Humanizer**: Upload a PDF to detect and remove AI writing patterns, producing natural prose
- **LaTeX Citation Reordering**: Upload a `.tex` file to automatically renumber bibliography entries sequentially ([1], [2], [3], ...)
- **Claim Normalization**: Standardizes metrics, conditions, and terminology
- **Contradiction Detection**: Identifies conflicting claims across papers
- **Research Gap Analysis**: Detects underexplored topics, missing methodologies, and evaluation gaps
- **Multi-Format Citations**: Generates BibTeX, APA, IEEE, and MLA citations
- **Persistent Memory**: Stores research results in a JSON-backed knowledge graph (no fragile pickle files)
- **Comprehensive Logging**: Detailed operation tracking for transparency

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd autonomous-research-system

# Install dependencies
pip install -r requirements.txt

# Create necessary directories
mkdir -p data/memory output
```

## Usage

### Basic Usage

```python
from src.research_system import AutonomousResearchSystem

# Initialize the system
system = AutonomousResearchSystem()

# Perform research on a topic
results = await system.research("Use of Graph Neural Networks in Drug Discovery")

# Access results
print(f"Papers found: {len(results.papers)}")
print(f"Claims extracted: {len(results.claims)}")
print(f"Research gaps: {len(results.research_gaps)}")
```

### Command Line Usage

```bash
# Run the main example
python main.py

# The system will research "Use of Graph Neural Networks in Drug Discovery"
# and save results to output/research_results.json
```

## Output Format

The system produces comprehensive research results including:

### Topic Map
- Main topic and subtopics
- Relevant methods and techniques
- Expected datasets
- Related research areas
- Search keywords

### Papers
- Title, authors, year, venue
- Relevance scores
- Abstract content
- DOI/ArXiv IDs when available

### Claims
- Structured claim statements
- Extracted metrics and values
- Experimental conditions
- Confidence scores
- Supporting evidence

### Contradictions
- Conflicting claims identification
- Contradiction types (direct, methodological, conditional)
- Severity scores
- Explanations

### Research Gaps
- Unexplored topics
- Methodological gaps
- Dataset limitations
- Evaluation gaps
- Priority scores

### Citations
- Multiple formats (BibTeX, APA, IEEE, MLA)
- Properly formatted references
- Venue-specific formatting

## Configuration

The system can be configured through `config.py`:

```python
# Storage settings
STORAGE_PATH = "data/memory"
OUTPUT_PATH = "output"

# Processing limits
MAX_PAPERS_PER_SOURCE = 50
MAX_CONCURRENT_REQUESTS = 5

# Quality thresholds
CLAIM_CONFIDENCE_THRESHOLD = 0.5
CONTRADICTION_THRESHOLD = 0.7
```

## Agent Details

### Topic Expansion Agent
- Decomposes research topics into subtopics
- Identifies relevant methods and datasets
- Generates search keywords
- Domain-specific knowledge for ML, drug discovery, etc.

### Paper Discovery Agent
- Searches ArXiv using REST API
- Simulates Semantic Scholar searches
- Ranks papers by relevance and impact
- Removes duplicates

### Claim Extraction Agent
- Pattern-based claim extraction
- Metric extraction (accuracy, precision, etc.)
- Dataset and condition identification
- Confidence scoring

### Claim Normalization Agent
- Standardizes metric names and units
- Normalizes experimental conditions
- Verifies claim strength
- Adds verification metadata

### Contradiction Detection Agent
- Compares claims pairwise
- Detects direct, methodological, and conditional contradictions
- Calculates severity scores
- Provides explanations

### Research Gap Detection Agent
- Identifies underexplored subtopics
- Detects methodological gaps
- Finds missing datasets
- Suggests research questions

### Citation Builder Agent
- Generates multiple citation formats
- Handles different venue types
- Proper author formatting
- DOI and URL inclusion

## Example Output

```json
{
  "topic": "Use of Graph Neural Networks in Drug Discovery",
  "summary": {
    "papers_analyzed": 3,
    "claims_extracted": 1,
    "contradictions_found": 0,
    "research_gaps_identified": 37
  },
  "papers": [
    {
      "title": "Semi-Supervised Classification with Graph Convolutional Networks",
      "authors": ["Thomas N. Kipf", "Max Welling"],
      "year": 2017,
      "venue": "ICLR",
      "relevance_score": 0.95
    }
  ]
}
```

## Logging

The system provides comprehensive logging:
- Agent operations and timing
- Error handling and warnings
- Memory usage statistics
- Research pipeline progress

Logs are saved to `research_system.log` and displayed in console.

## Memory System

The system maintains persistent memory:
- **Cache**: Fast in-memory storage for current session
- **Knowledge Graph**: Persistent nodes and edges
- **File Storage**: JSON and pickle serialization
- **Statistics**: Memory usage and performance metrics

## Limitations

- **Paper Access**: Currently limited to ArXiv and simulated sources
- **Claim Extraction**: Pattern-based, may miss complex claims
- **Language**: English-only processing
- **Evaluation**: No ground truth validation yet

## Future Enhancements

- Integration with more academic databases
- Advanced NLP for claim extraction
- Machine learning-based contradiction detection
- User interface for interactive research
- Ground truth evaluation datasets
- Multi-language support

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

[MIT](LICENSE)

## Citation

If you use this system in your research, please cite:

```bibtex
@software{autonomous_research_system,
  title={Autonomous Research Agent System},
  author={Aaris, Mohamed},
  year={2026},
  url={https://github.com/mohamedaaris/Research}
}
```