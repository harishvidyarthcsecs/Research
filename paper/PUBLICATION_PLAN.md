# VoRG Paper — Publication Plan

Working title (v2): **Reject-Before-Propagate: Build-Time Citation Gates for Agentic Literature-Synthesis Pipelines**

Authors: Harish Vidyarth N, A.L. Reshma, R. Divya — Dept. of CSE (Cyber Security), Rajalakshmi Engineering College.

Repo: https://github.com/harishvidyarthcsecs/Research

---

## 1. Status

| Item | State |
|---|---|
| `paper/main_v1_backup.tex` | original submission draft, preserved |
| `paper/main_v2.tex` | reframed, compiles (16 pp). Claims rescoped to match evidence. `% [PENDING]` markers where multi-topic + scored-ablation numbers go |
| Experiment infra (`--mode scored`, `run_matrix.py`, abstract backfill, downstream-error metrics) | being built by Codex (background) |
| Multi-topic corpora + gold | not started — needs snapshot (auto) + human adjudication |
| Journal target | to pick from §2 after the reframe is reviewed by co-authors |

## 2. Journal ranking

Assumes the reframe **plus** the matched scored-grounding ablation land. Multi-topic (3–5 topics) moves the paper up a tier.

### Primary targets

| Rank | Journal | Index / Q | APC | Review speed | Why |
|---|---|---|---|---|---|
| 1 | **PeerJ Computer Science** | Scopus, SCIE, Q2 (~IF 1.5) | ~$1,395; partial waivers; free w/ author membership | ~1 mo to first decision | Reproducibility-first ethos matches the paper. Released harness + gold files satisfy the raw-data requirement. Accepts focused-scope systems work. |
| 2 | **Journal of King Saud University – Computer & Information Sciences** | Scopus Q1, SCIE | **None** (KSU-funded) | moderate | Zero APC. Q1 Scopus. Common route for Indian authors. Elsevier `elsarticle` format. Good if budget is the hard constraint. |
| 3 | **Natural Language Engineering** (Cambridge) | Scopus, SCIE, Q2 (~IF 2.5) | none (OA optional ~$3k) | 2–4 mo | Engineering-NLP systems focus; welcomes pipeline/architecture contributions. Slower. |
| 4 | **IEEE Access** | JCR Q1 (~IF 3.4), mega-journal | ~$1,995 | 4–6 wk | Fast. Lenient on narrow eval for a clearly-scoped system paper. Reputation mixed. Fallback / speed option. |

### Lower bar / faster (if goal is "indexed now")

| Journal | Note |
|---|---|
| SN Computer Science (Springer) | Scopus, student-friendly, APC ~$1,290 w/ frequent waivers |
| Array (Elsevier, OA) | Scopus, low bar, APC ~$950 |

### Aspirational — only with strong multi-topic results + a 2nd domain + inter-annotator agreement

- **JASIST** — the topical venue; high bar.
- **Scientometrics** / **Quantitative Science Studies** — only if the journal-metadata-reconciliation subsystem is made central and evaluated on its own.

### Parallel, non-exclusive

- **arXiv cs.CL** — post as soon as co-authors sign off on v2. Independent of journal choice, gets a citable handle now.
- **Scholarly Document Processing (SDP) workshop** @ ACL/EMNLP/NAACL — short-paper version for fast peer feedback; does not block journal submission.

### Recommendation

arXiv now → **PeerJ Computer Science** primary (or **JKSU-CIS** if APC = $0 required) → **IEEE Access** fast fallback.

Keep `main_v2.tex` on the generic `article` class until the target is fixed, then port:
PeerJ → their LaTeX template · JKSU-CIS → `elsarticle` · IEEE Access → `IEEEtran` (double column).

## 2b. STRUCTURAL FINDING (2026-09-08) — resolve before experiments

The evaluation harness (`eval/run_eval.py` -> `AutonomousResearchSystem.research()`)
**never invokes** `literature_builder_agent`, `narrative_verifier`,
`EvidenceExtractionAgent`, or `synthesis_matrix_builder`. Those run only on the
web app's Literature Builder feature (`app.py:956`, `app.py:1027`).

Consequence: of the three "VoRG-gated subsystems" in the paper's §3, only
**contradiction detection** (the `likert_threshold` discard) is on the path the
evaluation actually measures. The flagship **evidence-grounded synthesis
sub-pipeline (Figure 1)** and **journal-metadata reconciliation** are described
but **not evaluated**. A reviewer will catch this.

Three ways forward (author decision):

| Option | What it means | Cost | Paper strength |
|---|---|---|---|
| A. Narrow claims | Paper = pattern + contradiction-threshold gate + gap-to-failure diagnostic. Evidence-synthesis / journal-metadata = "implemented, evaluation is future work". | low (mostly text) | honest, smaller; Tier B / IEEE Access |
| B. Extend harness | Drive `literature_builder_agent` on the frozen corpora in `run_eval.py`; add gold narrative-sentence annotations; then evidence + narrative gates are measurable and the scored ablation is genuinely matched across all three. | high (harness + ~1–2 h more annotation/topic) | strongest; Tier 1 |
| C. Refocus | Make the evidence-grounded synthesis sub-pipeline the core contribution; evaluate it directly (narrative verifier on/off, verbatim gate on/off); demote claims/contradiction/gap pipeline to context. | medium | clean single-subsystem study |

## 2c. HARNESS EXTENSION — build status (2026-09-08, Option B)

**Done + verified (Claude hand-built; Codex was unusable here):**

| File | Change | Verified |
|---|---|---|
| `src/agents/narrative_verifier.py` | `verify_sentence_scored` / `verify_paragraph_scored` — non-raising; unsupported sentence returned with `verified=False` | behaviour test: 1 good + 1 ghost-cite + 1 bare -> `unsupported=2`; reject path still raises |
| `src/agents/evidence_extraction_agent.py` | `grounding_mode` (`reject` default / `scored`), `GROUNDING_MODE` env; `_substring_ratio` grounding score; reject mode drops paraphrase-only + no-signal rows | imports; wiring check |
| `src/agents/literature_builder_agent.py` | `grounding_mode` ctor arg threaded to `EvidenceExtractionAgent` + `_build_cluster_paragraph_from_table` scored branch (no raise / no retry) | source check; import |
| `eval/matching.py` | `match_narrative(sentences, gold)` — precision/recall vs `gold_narrative.json` | 17 harness tests pass |
| `eval/run_eval.py` | `--mode scored`; `run_literature()` runs the synthesis sub-pipeline on the same results; `predictions["narrative"]`; `downstream_errors` block (unsupported sentences in narrative, retained FP contradictions, narrative build failed); 3 new `summary.md` columns | end-to-end smoke, exit 0 |

**Smoke run (`--mode scored --topics gnn-drug-discovery`):** completed, cost $0.008, 16 LLM calls, 1 parse failure. BUT `narrative_total_sentences = 0`, `evidence_rows_no_verbatim = 10` — the pilot corpus (9/10 papers with no abstract) produces no evidence rows with verbatim support, so the literature builder emits no verifiable narrative sentences and the gate has nothing to act on. **The scored-vs-reject ablation cannot be measured on the current pilot corpus.** Abstract backfill + at least one abstract-rich topic is now a hard prerequisite, not a nice-to-have.

**Also built (2026-09-08, later in the session):**
- `eval/snapshot_topic.py` — abstract backfill. Empty abstracts after the
  CrossRef merge are filled from Semantic Scholar Graph API (`DOI:` lookup,
  then title search) then OpenAlex (`abstract_inverted_index` reconstructed).
  stdlib `urllib`, 1 rps, raw JSON cached under `eval/topics/<slug>/_raw/`.
  Prints and writes `abstract_coverage` + `abstract_backfill` into `topic.json`.
  `--no-backfill` opts out. Also drops a `gold_narrative.json` template.
  Verified: S2 path returns a real abstract on a live DOI; OpenAlex path
  reachable (transient 429s handled by graceful `None`).
- `eval/run_matrix.py` — new. `--topics a,b --modes llm,pattern,scored,baseline
  --repeats 5`; each cell a subprocess (`run_eval` / `run_baseline`), parses
  `<run_dir>/<slug>/metrics.json`, writes `eval/results/matrix_<UTC>/aggregate.md`
  (per-topic mean +/- SD + pooled row per mode) with `git rev-parse HEAD` in the
  header. Verified: imports, `--help` parses.
- `eval/README.md` — documents `--mode scored`, the 3 downstream-error columns,
  `gold_narrative.json`, abstract backfill, `run_matrix`, groq provider pin.

**Harness extension: COMPLETE.** 17 harness tests pass; all eval modules import;
`--mode scored` ran end-to-end (exit 0). Nothing further to build here.

**Human blockers (all that's left before numbers exist):**
1. `python -m eval.snapshot_topic "<query>" --slug <slug>` for the pilot
   (re-snapshot, now with backfill) + 2-4 new abstract-rich topics
   (see section 4 for candidate slugs).
2. Per topic: correct `claims_to_annotate.csv` -> `gold_claims.json`; author
   `gold_gaps.json` (real gaps + hard negatives), `gold_contradictions.json`
   (hard negatives), and `gold_narrative.json` (sentences that should survive
   the gate). ~2-4 h/topic; co-author adjudication for inter-annotator kappa.
3. `python -m eval.run_matrix --topics <all slugs> --modes llm,pattern,scored,baseline --repeats 5`
4. Paste `aggregate.md` tables into `paper/main_v2.tex` sections 5.3-5.5, bump
   `\NumTopics` / `\NumRuns`, delete the `% [PENDING]` blocks, resolve the
   `% [PENDING]` sentences in the abstract and conclusion.

## 3. Remaining experiments (blocks a journal submission)

1. **Matched scored-grounding ablation** on the existing topic — `--mode scored`, 5 runs, plus re-run `llm` / `pattern` / `baseline` at 5 runs. Fills §5.4 (RQ1) + the downstream-error table. *Codex building the mode; Claude runs it.*
2. **Multi-topic** — 2–4 additional topics (see §4). Fills §5.3 (multi-topic F1) and §5.5 (gap-to-failure across topics, so the central claim no longer rests on one incident).
3. **Abstract coverage** — new snapshots use the Semantic Scholar / OpenAlex backfill so corpora are not 9/10 title-only. Report coverage per corpus.

Minimum viable for Tier-1 submission: #1 + #3 + at least **2** new topics (n=3 total).

## 4. Topic set

Pilot: `gnn-drug-discovery`.

Planned additions (applied-CS / security-adjacent — matches the department and keeps abstracts easy to source):

| Slug | Topic query |
|---|---|
| `dl-malware-detection` | deep learning for malware detection |
| `gnn-fraud-detection` | graph neural networks for fraud detection |
| `net-anomaly-detection` | anomaly detection in network traffic |
| `llm-code-generation` | large language models for code generation |

Trim to the first 2 if annotation capacity is tight (n=3 total still publishable at Tier 1 lower / Tier B).

## 5. Annotation protocol (per new topic)

Per `eval/README.md`, ~2–4 h/topic.

1. `python -m eval.snapshot_topic "<query>" --slug <slug>` — freezes corpus, backfills abstracts, writes `eval/topics/<slug>/`.
2. `python -m eval.bootstrap_gold --slug <slug>` — runs the pipeline once, drops `claims_to_annotate.csv` + `gold_*_draft.json`.
3. **Human step** — for each topic, two annotators (Reshma, Divya) independently:
   - keep / fix / delete each candidate claim against the source abstract (target: 8–15 verbatim gold claims/topic);
   - write 2–4 genuine research gaps (things truly absent from the corpus) + 2–4 hard negatives (gaps the corpus actually fills — these catch the ungated-stage failure);
   - label 3–5 contradiction candidate pairs, including hard negatives (same topic, compatible results).
4. Reconcile the two annotators → `gold_claims.json`, `gold_gaps.json`, `gold_contradictions.json`. Record Cohen's kappa.
5. Commit `papers.json` + gold + the repo commit hash.

If solo annotation (Harish only): skip kappa, keep the "single annotator team" note in §7 External validity.

## 6. Run matrix

```
python -m eval.run_matrix \
  --topics gnn-drug-discovery,dl-malware-detection,net-anomaly-detection[,...] \
  --modes llm,scored,pattern,baseline \
  --repeats 5
```
→ `eval/results/matrix_<UTC>/aggregate.md`. Port its tables into `main_v2.tex` §5.3–5.5, bump `\NumTopics` / `\NumRuns`, delete the `% [PENDING]` blocks.

## 7. Submission checklist

- [ ] Co-authors review `main_v2.pdf`; merge any Overleaf wording edits from the `main_edited` line into `main_v2.tex`.
- [ ] Experiments #1 + #3 + at least 2 topics done; `[PENDING]` sections filled.
- [ ] `\NumTopics` / `\NumRuns` updated; abstract + conclusion pending-sentences resolved.
- [ ] References: confirm every quartile caveat is still needed; verify DOIs.
- [ ] arXiv preprint posted; arXiv id added to camera-ready.
- [ ] Pick target journal; port to its class; write cover letter (lead with the gap-to-failure finding + released harness).
- [ ] Data availability: tag a repo release, cite the tag + commit hash.
- [ ] PRISMA-trAIce-style AI-use disclosure paragraph (the paper is literally about this — reviewers will expect it).
