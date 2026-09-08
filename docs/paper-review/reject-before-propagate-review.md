# Review — *Reject-Before-Propagate: Hard-Gated Citation Checks for Automated Literature Synthesis*

**Manuscript:** `~/Downloads/main_edited (1).pdf` — 16 pp, 29 references, 2 tables, 1 figure + 1 algorithm.
**Authors:** Harish Vidyarth N, Reshma A L, R. Divya — Rajalakshmi Engineering College (CSE — Cyber Security).
**Artifact:** `github.com/harishvidyarthcsecs/Research` (this repo).
**Reviewed:** 2026-09-08. Quartile / APC figures below cross-checked against the project's own
journal database (`data/journal_database.db`, 62,901 journals; SCImago + Scopus + DOAJ + publisher APC).

---

## 1. One-paragraph summary

The paper defines **Verify-or-Reject Grounding (VoRG)**: a pipeline stage is "verify-or-reject
grounded" if its *output type* cannot carry unverifiable content — either the stage is
deterministic over already-verified inputs, or an explicit check discards non-conforming output
before it propagates. This is contrasted with "scored grounding" (attach a confidence/flag a
downstream consumer may ignore). A reference implementation applies the pattern to three
subsystems of an 8-stage literature-synthesis pipeline (evidence-grounded synthesis,
contradiction detection, journal-metadata reconciliation); Algorithm 1 (`VoRG-Certify`) gives a
linear-time hash-indexed narrative certifier. The evaluation is deliberately narrow — one
gold-annotated topic, three repeated runs, three configurations (full LLM pipeline, rule-based
pattern-mode ablation, naive single-prompt baseline). The **headline result is a correspondence,
not a metric**: the two verify-or-reject-gated stages produce zero confirmed failures, while the
one ungated stage (research-gap detection) produces a confirmed false positive directly
contradicted by a paper already in the reviewed corpus.

---

## 2. Fit run — the project's own recommender

Feeding the abstract through `JournalRecommenderAgent().recommend(abstract, field="Scientific NLP")`
(`/journal-fit`) auto-detected the fields **Bioinformatics / Molecular Biology / Genomics** and
returned an all-bioinformatics shortlist (IEEE T. Computational Biology and Bioinformatics 82 %,
Briefings in Bioinformatics 80 %, Bioinformatics 78 %, …). **This is a miss, and it is
diagnostic for the tool, not the paper:** the recommender takes only a free-text abstract (no
title, no keyword list), its `_detect_broad_field` keyword map has no "citation grounding" /
"scientific NLP" / "scholarly document processing" entry, and OpenAlex `/sources` `search=`
on the residual concepts ("evidence", "synthesis", "extraction") pulls biomedical venues. Treat
the tool's output here as unusable for this paper and use the curated shortlist below. (This
also becomes improvement item I-8 — the recommender needs a title/keywords field and a
scientometrics/NLP field mapping.)

---

## 3. Where to publish — curated shortlist

The paper sits at the intersection of **scientometrics / research-software engineering /
scientific NLP**, with an honest negative result and a small single-topic evaluation. That
combination rules out top ML venues (they will desk-reject a 1-topic, 3-claim gold set) and
rules out pure-methodology stats journals. It fits venues that value *architecture patterns*,
*reproducible pipeline evaluation*, and *bibliometric tooling*.

### Tier A — best target now (realistic with a revision)

| Venue | Quartile / h | APC | Why it fits | Watch-outs |
|---|---|---|---|---|
| **Quantitative Science Studies (QSS)** — MIT Press / ISSI | Q1, h 38 | **$1,200** (verified) | Explicitly publishes bibliometric *infrastructure* and reconciliation methods; §3's journal-metadata subsystem and the "never-merge-silently" discipline are squarely in scope; open access, reasonable APC, methods-friendly reviewers. | Younger journal; will still want the evaluation broadened beyond one topic. |
| **Scientometrics** — Springer | Q1, h 167 | hybrid (~$3,290 OA, or free-to-publish paywalled) | The paper already cites it (refs 23, 26) for the exact gap it addresses — cross-database journal-metadata inconsistency and AI-for-scientometrics. Natural home for the reconciliation framing. | Reviewers there care less about the NLP internals; lead with the metadata/discrepancy contribution, not VoRG-Certify. |
| **PeerJ Computer Science** | Q2, h 72 | **$1,395** (verified) | OA, fast, explicitly welcomes reproducible-systems papers with released code + data; a negative/diagnostic result is acceptable there; the artifact is already public. | Lower prestige than QSS/Scientometrics; best if you want speed and an easy reproducibility story. |

### Tier B — credible, higher bar or narrower angle

| Venue | Quartile / h | APC | Angle |
|---|---|---|---|
| **Journal of the Association for Information Science and Technology (JASIST)** | Q1, h 181 | $3,480 (verified) | Broad iSchool venue; would want the human-factors / decision-support framing (systematic-review teams) foregrounded. |
| **Journal of Informetrics** — Elsevier | Q1, h 107 | $2,880 (verified) | Strong on metadata quality + measurement; narrower and more quantitative than QSS. |
| **Information Processing & Management** — Elsevier | Q1, h 149 | $3,350 (verified) | IR/NLP-for-scholarly-text; competitive, will push hard on evaluation scale. |
| **Natural Language Engineering** — Cambridge UP | Scopus ~Q2 (no SCImago row in DB) | hybrid | Practical NLP-systems venue; good fit for `VoRG-Certify` + the pipeline engineering, weaker fit for the scientometrics half. |

### Tier C — the software artifact, not the paper

- **Journal of Open Source Software (JOSS)** — for a *separate*, ~2-page software paper on the
  released pipeline + evaluation harness. Not a substitute for the research paper; a complement
  that gives the artifact a citable DOI.

### Workshops / short-paper routes (fastest feedback, lower stakes)

- **SDP — Scholarly Document Processing** (@ ACL/EMNLP/COLING) — the single most on-topic venue
  for "citation grounding as a build-time invariant"; ideal for a 4–8 pp version.
- **BIR — Bibliometric-enhanced IR** (@ ECIR) — for the metadata-reconciliation subsystem.
- **NLP+CSS** or an **SDP shared-task**-adjacent short paper — for the contradiction-judge
  abstention idea.
- **SIGIR / JCDL short paper** — if you want an ACM DL venue for the tooling.

### Not recommended

ACL/EMNLP/NeurIPS/ICLR main tracks, *TACL*, *Computational Linguistics* — the single-topic,
three-claim gold set and the "pattern mode ≈ LLM pipeline" result will read as under-evaluated
at those bars. Revisit after the multi-topic, multi-annotator evaluation the paper itself
promises.

**Recommendation:** target **QSS** (or **Scientometrics**) as the primary journal after
addressing I-1…I-4 below; in parallel, submit a short version to **SDP** now for fast expert
feedback; register the artifact with **JOSS**.

---

## 4. Rating

Scores are 1–10, calibrated to a mid-tier Q1 journal bar (QSS / Scientometrics).

| Axis | Score | Justification |
|---|---:|---|
| **Novelty & positioning** | **7** | The *distinction* — grounding as a property of the pipeline (reject-by-default) vs a property of the output (score) — is a genuinely useful reframing, cleanly tied to Saltzer & Schroeder fail-safe defaults. It is more a crisp synthesis + naming of existing practice (FEVER-style evidence checks, Self-RAG, PRISMA-trAIce) than a new mechanism, and the paper says so honestly. |
| **Methodological rigor / evidence strength** | **5** | Reproducible (fixed corpus, 3 repeats, released harness), temperature 0, parse-failures reported. But: one topic, three gold claims (all from the *single* corpus paper that had a real abstract), contradiction recall undefined, gap-detection n=3. The central claim (build-time reject > post-hoc score) is **not** tested by a matched ablation — the authors flag this themselves as the "primary open threat". The strongest evidence offered (the gap-to-failure correspondence) rests on a single observed false positive. |
| **Reproducibility** | **8** | Public repo, evaluation harness, gold files, frozen corpus, pinned provider/model, deterministic settings, documented implementation corrections. Among the paper's real strengths. Docker/env pin and an archived data snapshot would make it a 9–10. |
| **Writing & structure** | **8** | Clear, unusually candid about scope and limitations, good related-work coverage, each reference given its own attributed clause. Section 5 is slightly hard to follow (three configs × three metrics × caveats in prose); a results figure and a tightened §5.2 would help. |
| **Significance** | **6** | If the pattern holds up under a real evaluation, it is a useful design lens for anyone building agentic scientific-NLP pipelines, and the metadata-reconciliation instance is immediately practical. Current significance is capped by the evaluation being a case study on one corpus. |
| **Related-work coverage** | **8** | Broad and well-mapped (hallucination surveys, ALCE/CiteME, attribution frameworks, predatory-journal classifiers, SLR-automation reviews). Missing: an explicit tie to *runtime verification* / *design-by-contract* in software engineering (the pattern is essentially a pipeline-stage postcondition), and to *constrained decoding / grammar-constrained generation* as an alternative "can't emit bad output" route. |

**Overall: 6.5 / 10 — a solid, honest systems paper with a good idea and an under-powered
evaluation.** Realistic outcome *as-is*: reject-with-encouragement at a Q1 journal; accept at a
workshop (SDP) or PeerJ CS. With I-1…I-4 done: credible **major-revision → accept** at QSS /
Scientometrics.

---

## 5. Improvements — ordered by impact

**I-1. Run the matched scored-grounding ablation (highest impact).**
The paper's thesis is "reject beats score"; the current experiments only show "decomposition
helps". Add a fourth configuration: identical per-paper/per-claim decomposition, but each gated
stage emits its output **with a confidence score instead of rejecting**. Then compare downstream
error rates (unsupported sentences reaching the narrative; false-positive contradictions;
unflagged metric conflicts) under matched thresholds. This is the one experiment that tests the
title. The authors already scope it in §7 — promote it from "future work" to "done".

**I-2. Widen the evaluation corpus and annotators.**
One topic / three verbatim gold claims / one annotator team cannot support the effect sizes in
Table 2 (pattern-mode precision variance ±0.211). Target 5–10 topics, ≥2 independent annotators,
inter-annotator agreement reported, and at least a handful of corpora where papers have real
abstracts (the current corpus had 9/10 abstract-less records). Even 5 topics would move rigor
from 5 to 7.

**I-3. Extend verify-or-reject to gap detection and re-measure.**
The paper's best evidence is that the *unprotected* stage failed exactly where predicted. Close
the loop: implement the "reject a gap claim that contradicts a corpus title/abstract" check
(the repo already has the pieces — claim/paper matching, the contradiction judge), re-run, and
report whether the confirmed false positive disappears. A before/after on the same corpus is far
more persuasive than the correspondence argument alone.

**I-4. Turn §5.2 into a figure + tighten the prose.**
Add a results figure: three (or four, after I-1) configurations on the x-axis, grouped bars for
claim-F1 / contradiction FP-rate / gap precision@3, with error bars. Move the per-metric caveats
into the caption or a footnote. Right now the key numbers are buried in a dense paragraph.

**I-5. Report empirical timing for `VoRG-Certify`.**
Algorithm 1 is analyzed as O(n + M) but never timed. Add a small plot of certification wall-time
vs narrative length (and vs evidence-table size) against the linear-scan O(n·m) baseline, on
real runs. It makes the "removes the quadratic term" claim concrete and is cheap to produce.

**I-6. Connect to runtime verification / design-by-contract and constrained decoding.**
One paragraph in §2 or §4: VoRG's gated stage is a *postcondition* on a pipeline stage's output
type (runtime verification / DbC literature), and constrained/grammar-guided decoding is a
different route to "the stage cannot emit malformed output". Positioning against both sharpens
the novelty claim and pre-empts a reviewer raising them.

**I-7. Resolve the Q1 citation caveats using the project's own journal DB.**
Several references carry "journal quartile not independently confirmed at time of writing"
(refs 1, 15). The repo now has a 62,901-journal database with verified SCImago quartiles — use
it: e.g. *Mathematics* (ref 1) and the *JMIR* family (refs 4, 15) can be checked and the caveats
removed or made precise. Small, but it is a citation-grounding paper hedging its own citations.

**I-8. Fix the journal recommender before demoing it with this paper.**
`JournalRecommenderAgent` mis-classified this very abstract as bioinformatics (§2 above). Add a
title + keywords input, a scientometrics / scholarly-NLP / research-software entry to
`_detect_broad_field`, and fall back to the local journal DB (not just OpenAlex `search=`) when
field detection is low-confidence. Otherwise the paper's own tool visibly fails on the paper.

**I-9. Archive a data snapshot.**
"Data and Code Availability" points at a GitHub repo. Add a Zenodo/Figshare DOI for the frozen
corpus + gold files + harness at the reviewed commit, so the evaluation is reproducible even if
the repo moves. Bumps reproducibility to 9–10 and is a one-afternoon task.

**I-10. Minor.**
(a) Define "confirmed failure" once, early — it carries a lot of weight in §6. (b) The naive
baseline is described in both §5.1 and §5.2; consolidate. (c) State the annotator count and
their independence from the authors explicitly (currently "the present authors" — a
conflict-of-interest reviewer will flag gold annotation by the authors of the system under
test; at minimum acknowledge it as a limitation, ideally add one external annotator). (d)
`main_edited (1).pdf` — give the file a real name before submission.

---

## 6. Bottom line

Good idea, honest paper, real artifact, thin evaluation. Do **I-1** (matched ablation) and
**I-2** (more topics/annotators) and this is a publishable Q1 scientometrics/scientific-NLP
paper. Until then, a **workshop (SDP)** submission plus a **PeerJ CS** or **QSS** full
submission with the ablation added is the fastest credible path, and **JOSS** gives the software
a citable identity in parallel.
