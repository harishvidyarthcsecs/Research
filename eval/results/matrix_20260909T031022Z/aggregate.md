# Evaluation matrix — 20260909T031022Z

- commit: `847d26cc048c2590f23920ac57c677182b4359af`
- topics: gnn-drug-discovery
- modes: llm, pattern, scored, baseline
- repeats per cell: 3
- values: mean ± population SD across repeats

## mode: llm

| topic | claim_precision | claim_recall | claim_f1 | contra_fp_rate_neg | gap_recall | gap_p_at_3 | unsupported_sentences_in_narrative | retained_fp_contradictions | narrative_build_failed | cost_usd | parse_failures |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gnn-drug-discovery | 0.116 ± 0.041 | 0.889 ± 0.157 | 0.205 ± 0.068 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.014 ± 0.002 | 2.333 ± 0.471 |
| **pooled** | 0.116 ± 0.041 | 0.889 ± 0.157 | 0.205 ± 0.068 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.014 ± 0.002 | 2.333 ± 0.471 |

## mode: pattern

| topic | claim_precision | claim_recall | claim_f1 | contra_fp_rate_neg | gap_recall | gap_p_at_3 | unsupported_sentences_in_narrative | retained_fp_contradictions | narrative_build_failed | cost_usd | parse_failures |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gnn-drug-discovery | 0.024 ± 0.034 | 0.222 ± 0.314 | 0.043 ± 0.061 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.007 ± 0.000 | 1.667 ± 0.471 |
| **pooled** | 0.024 ± 0.034 | 0.222 ± 0.314 | 0.043 ± 0.061 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.007 ± 0.000 | 1.667 ± 0.471 |

## mode: scored

| topic | claim_precision | claim_recall | claim_f1 | contra_fp_rate_neg | gap_recall | gap_p_at_3 | unsupported_sentences_in_narrative | retained_fp_contradictions | narrative_build_failed | cost_usd | parse_failures |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gnn-drug-discovery | 0.278 ± 0.208 | 0.667 ± 0.471 | 0.389 ± 0.283 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.007 ± 0.002 | 1.333 ± 1.247 |
| **pooled** | 0.278 ± 0.208 | 0.667 ± 0.471 | 0.389 ± 0.283 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.007 ± 0.002 | 1.333 ± 1.247 |

## mode: baseline

| topic | claim_precision | claim_recall | claim_f1 | contra_fp_rate_neg | gap_recall | gap_p_at_3 | unsupported_sentences_in_narrative | retained_fp_contradictions | narrative_build_failed | cost_usd | parse_failures |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gnn-drug-discovery | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.002 ± 0.000 | 0.000 ± 0.000 |
| **pooled** | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.002 ± 0.000 | 0.000 ± 0.000 |
