# Multi-topic evaluation — manual aggregate (PRELIMINARY)

- **Status**: PRELIMINARY. `repeats=1` per configuration (not the pilot's 3).
- **Provider**: local Ollama, `qwen2.5:7b`, temperature 0.2–0.3 depending on stage.
  `qwen2.5:14b` was also tried on the reject-mode narrative failure (dl-malware
  smoke test) and showed the same failure class (an uncited fragment), so the
  matrix stayed on the faster 7b model.
- **Modes run**: `llm` (reject), `scored`, `baseline`. `pattern` mode omitted for
  the 3 new topics (the pilot's Table III already carries the pattern-mode point).
- **Corpus trims**: `net-anomaly-detection` 20→8 papers, `gnn-fraud-detection`
  10→8 papers (gold-referenced papers kept first, then abstract-bearing fillers).
  `gnn-drug-discovery` (pilot) and `dl-malware-detection` untouched.
- **Abstract coverage**: gnn-drug 1/10 (pilot, unchanged), dl-malware 0.556,
  net-anomaly 1.0, gnn-fraud 1.0.
- **Commit**: `847d26c` base (this effort uncommitted at aggregate time).
- **Cells completed**: 4 topics × (llm, scored, baseline) = 12/12. Full matrix.

## Downstream-error table (reject vs scored)

Reject mode never lets an unsupported sentence reach the final synthesis by
construction — on 3 of 4 topics it enforces that by **failing the build
outright** (0 sentences reach the reader) rather than by passing every sentence.
Scored mode keeps every sentence and flags the unverifiable ones, so it always
completes and its leak count is directly observable.

| Topic | Reject (llm) | Scored: unsupported / total |
|---|---|---|
| GNN drug discovery (pilot) | 0 / 4 (clean build) | 1 / 5 |
| DL malware detection | BUILD-FAILED (0 reach reader) | 8 / 24 |
| GNN fraud detection | BUILD-FAILED (0 reach reader) | 29 / 76 |
| Net. anomaly detection | BUILD-FAILED (0 reach reader) | 17 / 66 |
| **Pooled (3 new topics)** | **0 reach reader, all 3** | **54 / 166** |

Root cause of the reject-mode build failures: the LLM (qwen2.5:7b, and
qwen2.5:14b on a retest) reliably writes one uncited framing/motivating sentence
(e.g. "The application of advanced graph neural networks in fraud detection has
shown promising results.") per synthesized paragraph; the reject gate's
"every sentence must carry a `\cite{}` key" check has no tolerance for this and
halts the whole build. A correction-retry that explicitly names the citation
requirement was added (`literature_builder_agent.py`) and did not change the
outcome on either model size — accepted as a genuine finding rather than
engineered away further.

## Gap-to-failure correspondence (ungated gap stage vs corpus)

Hand-verified against each topic's own `papers.json` — see
`~/.claude/jobs/483c008f/tmp/gap_verification_worksheet.md` for the per-gap
reasoning and cited paper titles.

| Topic | Gaps emitted | Corpus-contradicted (hand-verified) | Gated-stage contradicted |
|---|---|---|---|
| GNN drug discovery (pilot) | 2 | 1 | 0 |
| DL malware detection | 3 | 2 | 0 |
| GNN fraud detection | 4 | 3 | 0 |
| Net. anomaly detection | 5 | 3 | 0 |
| **Total** | 14 | **9** | **0** |

Every contradicted gap: the ungated research-gap stage claims "no work on X"
for an X the topic's own frozen corpus already contains a paper about. The two
gated stages (claim extraction, contradiction detection) produced zero
corpus-contradicted output in every topic — the correspondence between
"ungated" and "where the failure lands" held on all four topics, not just the
pilot.

## Baseline (naive single-LLM, all 4 topics)

| Topic | Claim F1 (vs gold)\* | LLM calls | Cost |
|---|---|---|---|
| GNN drug discovery (pilot, adjudicated gold) | 0.333 | 1 | $0 |
| DL malware detection | 0.000 | 1 | $0 |
| GNN fraud detection | 0.000 | 1 | $0 |
| Net. anomaly detection | 0.154 | 1 | $0 |

\* For the 3 new topics this is a **reference number only** — F1 against
bootstrapped, non-adjudicated gold is not a claimed result per the integrity
rule. Only the pilot's F1 (Table III, adjudicated) is a reported claim.

## Run directories

- llm (reject): `20260910_140610_llm` (gnn-drug), `20260910_144408_llm`
  (dl-malware, gnn-fraud, net-anomaly)
- scored: `20260911_135838_scored` (gnn-drug, dl-malware),
  `20260911_141032_scored` (gnn-fraud, net-anomaly)
- baseline: `20260911_172355_baseline` (all 4)
