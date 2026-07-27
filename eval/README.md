# Evaluation Harness

Quantitative evaluation of claim extraction, contradiction detection, and
research-gap detection against manually authored gold annotations, plus a
naive single-LLM baseline for comparison.

## Workflow

1. **Snapshot a topic** (runs discovery once, freezes the corpus):
   ```bash
   python -m eval.snapshot_topic "graph neural networks drug discovery" --slug gnn-drug
   ```
2. **Author gold data** in `eval/topics/<slug>/` (schemas below). Start from
   `claims_to_annotate.csv` — correct/keep pipeline-extracted claims instead
   of writing them from scratch (~2–4 h per topic).
3. **Run the pipeline eval** (uses the frozen corpus, so no API traffic to
   paper sources):
   ```bash
   LLM_PROVIDER=xai python -m eval.run_eval             # full system
   LLM_PROVIDER=xai python -m eval.run_eval --mode pattern  # rule-based ablation
   ```
4. **Run the baseline**:
   ```bash
   LLM_PROVIDER=xai python -m eval.run_baseline
   ```
5. Compare `eval/results/<run_id>/summary.md` tables. Run each configuration
   3 times and report mean/variance (providers are nondeterministic even at
   temperature 0).

## Gold data schemas

### `gold_claims.json`
```json
[
  {"paper_id": "arxiv_0000_00000", "statement": "Model X improves accuracy by 12% on Dataset Y"}
]
```
`paper_id` must match the `paper_id` field in `papers.json`.

### `gold_contradictions.json`
```json
{
  "positives": [
    {
      "paper_id_1": "arxiv_0000_00000",
      "claim_text_1": "Method A outperforms baselines on Dataset Y",
      "paper_id_2": "10_0000_example_doi",
      "claim_text_2": "Method A fails to beat simple baselines on Dataset Y",
      "label": "contradiction",
      "notes": "same dataset, opposite outcome"
    }
  ],
  "negatives": [
    {
      "paper_id_1": "...",
      "claim_text_1": "...",
      "paper_id_2": "...",
      "claim_text_2": "...",
      "label": "no_contradiction",
      "notes": "related topic, but results are on different tasks — no conflict"
    }
  ]
}
```
**Negatives matter**: pick *hard* negatives (same topic, superficially
conflicting wording, genuinely compatible). They are the basis of the
false-positive-rate column.

### `gold_gaps.json`
```json
[
  {
    "description": "No study evaluates methods on Dataset Z",
    "gap_type": "dataset",
    "keywords": ["Dataset Z", "evaluation", "benchmark"]
  }
]
```
`gap_type` ∈ `methodological | dataset | unexplored_subtopic | evaluation | contradiction_driven`.

## Matching rules (how predictions are scored)

- **Claims**: predicted claim matches gold iff same `paper_id` AND fuzzy
  ratio (difflib, normalized text) ≥ 0.6. Greedy one-to-one assignment →
  precision/recall/F1.
- **Contradictions** (primary, paper-pair level): a predicted unordered paper
  pair that equals a gold positive is a TP; equal to a gold negative is an
  explicit FP; pairs not labeled in gold are excluded from precision/recall
  and reported as "unlabeled volume". Secondary strict scoring additionally
  requires both claim texts to fuzzy-match (≥ 0.6, either ordering).
- **Gaps**: `gap_type` must match AND (description fuzzy ratio ≥ 0.5 OR ≥ 2
  gold keywords appear in the prediction). Reported as precision@3,
  precision@k (default 5), and recall of gold gaps.

## Reproducibility checklist for paper runs

- Pin the provider: `LLM_PROVIDER=xai` (model `grok-3-mini`), temperature 0.0
  (pipeline default).
- Commit the frozen `papers.json` snapshots.
- Record the repo commit hash with each results directory.
- Report per-topic cost (`summary.md` cost column) and parse-failure counts.
- 3 repeats per configuration; report mean and variance.
