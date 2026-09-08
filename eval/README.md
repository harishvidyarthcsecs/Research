# Evaluation Harness

Quantitative evaluation of claim extraction, contradiction detection, and
research-gap detection against manually authored gold annotations, plus a
naive single-LLM baseline for comparison.

## Workflow

1. **Snapshot a topic** (runs discovery once, freezes the corpus, then
   backfills any missing abstracts from Semantic Scholar / OpenAlex so the
   corpus is not title-only):
   ```bash
   python -m eval.snapshot_topic "graph neural networks drug discovery" --slug gnn-drug
   python -m eval.snapshot_topic "..." --slug ... --no-backfill   # skip the backfill
   ```
   `topic.json` records `abstract_coverage` (fraction of papers with abstract
   text) and an `abstract_backfill` summary. A low coverage is a corpus
   limitation to report — the evidence-grounded synthesis metrics below are
   meaningless when the corpus has no abstract text to ground against.
2. **Author gold data** in `eval/topics/<slug>/` (schemas below). Start from
   `claims_to_annotate.csv` — correct/keep pipeline-extracted claims instead
   of writing them from scratch (~2–4 h per topic).
3. **Run the pipeline eval** (uses the frozen corpus, so no API traffic to
   paper sources):
   ```bash
   LLM_PROVIDER=groq python -m eval.run_eval                 # full system, gate on
   LLM_PROVIDER=groq python -m eval.run_eval --mode pattern  # rule-based ablation
   LLM_PROVIDER=groq python -m eval.run_eval --mode scored   # matched scored-grounding ablation
   ```
   `--mode scored` runs the same decomposition and LLM calls as the default,
   but the evidence-grounded synthesis sub-pipeline keeps unverifiable
   evidence rows and narrative sentences (with a grounding score / `verified`
   flag) instead of rejecting them. The default (`llm`) and `pattern` enforce
   the build-time citation gate.
4. **Run the baseline**:
   ```bash
   LLM_PROVIDER=groq python -m eval.run_baseline
   ```
5. Compare `eval/results/<run_id>/summary.md` tables. Run each configuration
   at least 3 times (5 for paper runs) and report mean/variance (providers are
   nondeterministic even at temperature 0). To run the whole matrix at once:
   ```bash
   python -m eval.run_matrix --topics slug1,slug2 \
       --modes llm,pattern,scored,baseline --repeats 5
   ```
   → `eval/results/matrix_<UTC>/aggregate.md` with per-topic mean ± SD and a
   pooled row per mode, and the repo commit hash in the header.

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

### `gold_narrative.json` (optional)

Sentences that *should* survive the citation-verification gate, i.e. genuine
corpus-supported statements the evidence-grounded synthesis narrative is
expected to produce:
```json
[
  {"text": "GNNs applied to ADMET prediction improved ROC-AUC over descriptor baselines on the MoleculeNet benchmark"}
]
```
Only used when present. Drives the `narrative` precision/recall block
(precision = fraction of `verified` sentences that match a gold sentence;
recall = fraction of gold sentences matched by a `verified` sentence, fuzzy
ratio ≥ 0.5).

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

## Downstream-error columns (verify-or-reject vs scored grounding)

`summary.md` and `metrics.json["downstream_errors"]` add, for every mode:

- **`unsupported_sentences_in_narrative`** — final-narrative sentences whose
  citation does not resolve to a verified evidence row. `0` by construction
  under the gate (`llm` / `pattern`); `> 0` possible under `scored`.
- **`retained_fp_contradictions`** — asserted contradictions whose paper pair
  matches a gold *negative*.
- **`narrative_build_failed`** — under the gate, one unsupported sentence
  aborts the whole synthesis build; this flags that. `scored` never fails this
  way (it keeps the sentence instead).

## Reproducibility checklist for paper runs

- Pin the provider: `LLM_PROVIDER=groq` (model `openai/gpt-oss-120b`),
  temperature 0.0 (pipeline default) / 0.3 where a synthesis call sets its own.
- Snapshot with abstract backfill; record `abstract_coverage` per topic.
- Commit the frozen `papers.json` snapshots and the `_raw/` API cache.
- Record the repo commit hash with each results directory
  (`run_matrix` writes it into `aggregate.md`).
- Report per-topic cost (`summary.md` cost column) and parse-failure counts.
- 5 repeats per configuration for paper runs; report mean and SD.
