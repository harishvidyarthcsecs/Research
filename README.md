# Autonomous Research Agent System

A multi-agent research system that autonomously performs academic and technical
research end-to-end, with **dedicated, separately-measured contradiction
detection and research-gap detection agents** — most competing autonomous
literature-review systems bury both inside a single narrative "writing" agent
and never evaluate them on their own. This repo treats them as first-class,
benchmarked tasks instead.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/harishvidyarthcsecs/Research/actions/workflows/ci.yml/badge.svg)](https://github.com/harishvidyarthcsecs/Research/actions)

## Why this exists

Autonomous multi-agent research systems (AI-Researcher, FARS, PaperOrchestra,
Agent Laboratory, LiRA) have converged on the same weak point: contradiction
detection and research-gap detection are narrative side-effects of literature
review, not tasks that are separately measured. Even the most advanced
dedicated contradiction system (ContraCrow, built on PaperQA2) evaluates
against human experts rather than a fixed benchmark, and adjacent work shows
GPT-4-class models perform only slightly better than chance at contradiction
detection. Gap detection has essentially no benchmark at all.

| System | Contradiction detection | Gap detection | Ground-truth eval | Real API sources |
|---|---|---|---|---|
| AI-Researcher | Implicit, inside idea generation | Implicit | No | Partial |
| FARS | No | No | No | Yes (expensive) |
| PaperOrchestra | No (literature synthesis only) | No | Human side-by-side only | Yes |
| ContraCrow (PaperQA2) | Yes, dedicated, Likert-scale | No | Human expert eval, no fixed benchmark | Yes |
| LiRA | No | No | Automated metrics only | Yes |
| **This system** | Yes, dedicated agent | Yes, dedicated agent | Gold-standard benchmark + naive-baseline comparison | Yes |

This is informal positioning based on the published descriptions of each
system, not a peer-reviewed comparison — see [Evaluation](#evaluation) for
what's actually measured here today.

## System Architecture

### Core research pipeline (8 stages)

Each stage below is an AI-based agent — LLM-driven by default, with a
transparent rule-based fallback/ablation mode for reproducibility and for
when no LLM provider is configured. The only classical-ML component in the
whole system is a TF-IDF cosine-similarity prefilter used purely to narrow
down candidate claim pairs before the LLM judges them — it never makes a
final decision on its own.

1. **Topic Expansion Agent** — LLM decomposes the topic into subtopics,
   methods, datasets, related areas, and search keywords (`TOPIC_MODE=llm`,
   default when a provider is configured). Falls back to a hardcoded
   5-domain keyword dictionary (`TOPIC_MODE=rules`) with no API key.
2. **Paper Discovery Agent** — searches ArXiv, Semantic Scholar (Graph API),
   and CrossRef via their real APIs; ranks by relevance/impact; fuzzy
   title+year dedup across sources with provenance merging; backoff on rate
   limits.
3. **Claim Extraction Agent** — LLM-based structured extraction (JSON claims
   with evidence sentences) via the shared `llm_client`; regex fallback when
   no provider is configured.
4. **Claim Normalization Agent** — standardizes metric names, units, and
   experimental conditions (rule-based).
5. **Contradiction Detection Agent** — ContraCrow-style two-stage detection:
   a TF-IDF candidate-pair prefilter selects the top-K most similar
   cross-paper claim pairs, then an LLM judges each pair on an 11-point
   Likert scale (1 = strong support, 11 = strong contradiction) with
   verbatim evidence sentences. Pattern-matcher ablation via
   `CONTRADICTION_MODE=pattern`.
6. **Research Gap Detection Agent** — builds a corpus summary (subtopic/
   method/dataset coverage, publication-year histogram, unresolved
   contradictions) and asks an LLM for typed, evidence-grounded gaps scored
   by importance × tractability, returning only the top-k. Rule-based
   ablation via `GAP_MODE=rules`.
7. **Citation Builder Agent** — generates BibTeX, APA, IEEE, and MLA
   citations (rule-based formatting).
8. **Long-Term Memory** — JSON-backed persistent knowledge graph and cache
   (`MemoryStore`), no fragile pickle files.

Every LLM-backed agent falls back gracefully to its rule-based mode on any
provider failure (bad key, rate limit, network error) rather than crashing
the run — this is what makes the pipeline usable as a live prototype instead
of a research-only harness.

### Standalone feature agents

Wired into the web app with their own routes and pages, not part of the core
pipeline above:

- **Literature Builder Agent** — clusters claims by theme/method, then an LLM
  synthesizes each literature-review paragraph strictly grounded in the
  retrieved paper abstracts, with inline `\cite{}` keys (`LITERATURE_MODE=llm`,
  default). Falls back to the original sentence-extraction/templating
  pipeline (`LITERATURE_MODE=rules`) with no API key.
- **Humanizer Agent** — LLM rewriting to remove AI-writing patterns from
  uploaded text/PDFs.
- **LaTeX Citation Reorder** — regex-based `.tex` bibliography renumbering
  (no LLM needed).
- **Reference Validator** — validates/corrects uploaded reference files via
  CrossRef DOI/title lookups.
- **Plagiarism Checker Agent** — searches OpenAlex/CrossRef/Semantic Scholar
  for similar text, keyword scoring, plus optional LLM-based sentence-level
  similarity analysis.
- **Journal Recommender Agent** — OpenAlex + CrossRef + a curated,
  Scimago-verified quartile lookup (108 journals), with an LLM fallback for
  journals outside that list.
- **Abstract Screener Agent** — LLM-based systematic-review abstract
  screening (include/exclude/maybe) against user-supplied criteria.
- **Checklist Agent** — LLM + OpenAlex-based pre-submission checklist
  generator.
- **Grant Writer Agent** — LLM-based grant-writing assistant with
  funder-specific templates.
- **Citation Network Agent** — builds citation networks from OpenAlex
  (primary) with Semantic Scholar fallback.

## Features

- **Autonomous Research Pipeline**: end-to-end research with minimal user input
- **Multi-Source Paper Discovery**: real ArXiv, Semantic Scholar, and CrossRef APIs
- **LLM-Based Topic Expansion, Claim Extraction & Literature Synthesis**: with
  transparent rule-based fallbacks, never a silent crash on a bad API key
- **Contradiction Detection**: ContraCrow-style Likert-scale LLM judge over a
  TF-IDF-prefiltered candidate set
- **Research Gap Analysis**: typed, ranked, evidence-grounded gaps
- **Benchmark Dashboard**: `/benchmark` — run the dedicated pipeline against a
  naive single-LLM baseline on a frozen worked-example corpus and see the
  comparison live in the browser
- **AI Writing Humanizer**, **LaTeX Citation Reordering**, **Reference
  Validator**, **Plagiarism Checker**, **Journal Fit Recommender**,
  **Abstract Screener**, **Pre-Submission Checklist**, **Grant Writer**,
  **Citation Network Explorer**
- **Multi-Format Citations**: BibTeX, APA, IEEE, MLA
- **Persistent Memory**: JSON-backed knowledge graph (no fragile pickle files)

## Installation

```bash
git clone https://github.com/harishvidyarthcsecs/Research.git
cd Research

python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
mkdir -p data/memory output
```

Create a `.env` file with at least one LLM provider key — see
[`src/agents/llm_client.py`](src/agents/llm_client.py) for the full priority
order (xAI Grok → Anthropic Claude → Groq → local Ollama → OpenRouter).
Without any key configured, every LLM-backed agent runs in its rule-based
fallback mode instead.

## Usage

### Web app

```bash
python app.py
# open http://localhost:5000
```

### Programmatic

```python
from src.research_system import AutonomousResearchSystem

system = AutonomousResearchSystem()
results = await system.research("Use of Graph Neural Networks in Drug Discovery")

print(f"Papers found: {len(results.papers)}")
print(f"Claims extracted: {len(results.claims)}")
print(f"Research gaps: {len(results.research_gaps)}")
print(f"LLM cost: ${results.usage['estimated_cost_usd']}")
```

## Output Format

### Topic Map
Main topic, subtopics, relevant methods/techniques, expected datasets,
related research areas, search keywords.

### Papers
Title, authors, year, venue, relevance score, abstract, DOI/ArXiv ID.

### Claims
Structured statement, extracted metrics/values, experimental conditions,
confidence score, evidence sentence.

### Contradictions
Conflicting claim pairs, Likert score (1–11), severity, verbatim evidence
from both papers, explanation.

### Research Gaps
Typed (`methodological | dataset | unexplored_subtopic | evaluation |
contradiction_driven`), ranked, scored by importance × tractability, with
supporting evidence.

### Citations
BibTeX, APA, IEEE, MLA, with venue-specific formatting.

## Configuration

Mode toggles (env vars), each defaulting to `llm` when a provider is
configured and falling back to a rule-based mode otherwise:

```bash
TOPIC_MODE=llm|rules            # Topic Expansion Agent
CONTRADICTION_MODE=llm|pattern  # Contradiction Detection Agent
GAP_MODE=llm|rules              # Research Gap Detection Agent
LITERATURE_MODE=llm|rules       # Literature Builder Agent
LLM_PROVIDER=xai|anthropic|groq|ollama|openrouter  # pin a provider (reproducible eval runs)
```

Storage/limits are configured in `config.py`:

```python
STORAGE_PATH = "data/memory"
OUTPUT_PATH = "output"
MAX_PAPERS_PER_SOURCE = 50
MAX_CONCURRENT_REQUESTS = 5
CLAIM_CONFIDENCE_THRESHOLD = 0.5
CONTRADICTION_THRESHOLD = 0.7
```

## Example Output

```json
{
  "topic": "Use of Graph Neural Networks in Drug Discovery",
  "summary": {
    "papers_analyzed": 20,
    "claims_extracted": 48,
    "contradictions_found": 3,
    "research_gaps_identified": 7
  },
  "usage": { "calls": 15, "prompt_tokens": 42150, "completion_tokens": 6300, "estimated_cost_usd": 0.0158 }
}
```

## Logging

Agent operations, timing, error handling, and memory statistics are logged to
`research_system.log` and the console.

## Memory System

JSON-backed persistent storage: fast in-memory cache for the current session,
a persistent knowledge graph of nodes/edges, and file-backed statistics — no
pickle files.

## Evaluation

A ground-truth evaluation harness lives in [`eval/`](eval/README.md):

1. **`python -m eval.snapshot_topic`** freezes a real paper corpus per topic
   and exports pipeline-extracted claims to a CSV for correction.
2. **`python -m eval.bootstrap_gold`** auto-drafts candidate gold claims and
   contradiction positives/negatives from a real pipeline run against that
   frozen corpus (high/low Likert-score pairs), each tagged
   `"status": "REVIEW_NEEDED"` — never treated as verified ground truth until
   a human reviews and copies accepted items into the real `gold_*.json`
   files. This turns gold-data authoring into correction instead of writing
   from scratch.
3. **`python -m eval.run_eval`** runs the full pipeline (or `--mode pattern`
   ablation) against the frozen corpus and scores claim extraction
   (precision/recall/F1), contradiction detection (paper-pair
   precision/recall + false-positive rate on hard negatives), and gap
   detection (precision@k + recall).
4. **`python -m eval.run_baseline`** runs a naive single-LLM baseline
   (one prompt, one pass) for comparison, scored with the same matchers.
5. The **`/benchmark`** page in the web app runs the same pipeline-vs-baseline
   comparison live, on demand, in the browser.

See `eval/README.md` for gold-data schemas, matching rules, and the
reproducibility checklist (pinned provider, temperature 0.0, 3 repeats).

**Status**: the harness (matching logic, usage tracking, ablation modes) is
implemented and unit-tested (`tests/test_eval_harness.py`); one worked
example (`eval/topics/gnn-drug-discovery/`, real ArXiv/Semantic
Scholar/CrossRef papers) is snapshotted. Full 8–10 topic gold-standard
authoring (~2–4h/topic of human correction) is in progress, not yet complete
— treat any precision/recall numbers as illustrative until that's done.

## Limitations

- **Paper Access**: ArXiv, Semantic Scholar, and CrossRef (PubMed disabled
  until real abstract retrieval is implemented); title + abstract only, no
  full text, which caps contradiction/claim recall
- **Claim Extraction**: LLM-based when a provider is configured, else regex
  fallback, which may miss complex claims
- **Language**: English-only processing
- **Provider nondeterminism**: LLM outputs vary run-to-run even at
  temperature 0; report mean/variance over repeats
- **Benchmark coverage**: gold-standard data currently covers 1 worked-example
  topic; broader coverage is in progress (see Evaluation above)

## Future Enhancements

- Full 8–10 topic gold-standard benchmark authoring and 3-repeat evaluation runs
- Integration with more academic databases (PubMed full-text, Springer, Elsevier)
- Multi-language support
- User accounts / saved research history beyond local JSON storage

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
  author={Harish Vidyarth N},
  year={2026},
  url={https://github.com/harishvidyarthcsecs/Research}
}
```
