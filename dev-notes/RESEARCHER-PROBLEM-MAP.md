# Researcher Lifecycle Problem Map + Build Roadmap

Evidence-backed map of problems researchers hit across a career, scored against
what this app does today, plus a build order.

Sources at bottom. Written 2026-08-02.

---

## LEGEND

**Status — does the app solve it today?**

| Mark | Meaning |
|---|---|
| `[X]` | Solved. Feature exists and works |
| `[~]` | Partial. Feature exists but shallow, slow, or unreliable |
| `[ ]` | Not solved. No feature |
| `[!]` | Not solvable by this app (structural/political/funding) — document, don't build |

**Impact** — how many researchers hurt, how badly: `H` high / `M` medium / `L` low
**Effort** — build cost: `S` <1 day / `M` 1–3 days / `L` 1–2 weeks / `XL` >2 weeks
**Moat** — hard for competitors to copy: `Y` / `N`

Priority = Impact × Moat ÷ Effort. `H`-impact + `[ ]`-status + `S`/`M` effort ships first.

---

## PHASE 1 — Getting started (no idea how to research)

Directly matches "50% of our faculty are not into research".

| # | Problem | Status | Impact | Effort |
|---|---|---|---|---|
| 1.1 | No formal mentorship — Indian academia has "almost non existent" faculty mentoring, no formal programs even at top institutions | `[ ]` | H | M |
| 1.2 | No research training facilities — 45.9% of faculty in an Indian medical-college study named this the top barrier | `[ ]` | H | M |
| 1.3 | Doesn't know how to pick a researchable topic (too broad / saturated / no data) | `[~]` topic expansion exists, no feasibility scoring | H | M |
| 1.4 | Doesn't know where papers live (ArXiv vs Scopus vs PubMed vs Scholar) | `[ ]` | H | S |
| 1.5 | Doesn't know how to download papers legally | `[ ]` | H | M |
| 1.6 | Poor computer/software skills — cited alongside mentorship as a barrier domain | `[ ]` | M | M |
| 1.7 | No idea what a "good" paper looks like (IMRaD, novelty bar) | `[ ]` | M | S |
| 1.8 | Doesn't know the publication ladder (conference vs journal vs preprint) | `[ ]` | M | S |

## PHASE 2 — Literature discovery and access

| # | Problem | Status | Impact | Effort |
|---|---|---|---|---|
| 2.1 | **Paywalls** — no full text without institutional subscription | `[ ]` | H | M |
| 2.2 | Doesn't know a legal free copy exists — Unpaywall indexes 30M+ articles across 50,000+ OA sources | `[ ]` | H | S |
| 2.3 | Doesn't know whether *their* institution has access before hitting the paywall | `[ ]` | H | L |
| 2.4 | No idea which institutions do have access (for co-author/ILL requests) | `[ ]` | H | L |
| 2.5 | Volume overload — publication rate outpaces what any team can screen | `[~]` discovery caps at 50/source | H | M |
| 2.6 | Search recall poor — one keyword set misses whole subfields | `[~]` | H | M |
| 2.7 | Title+abstract only, no full text → weak claim/contradiction extraction | `[~]` known limitation | H | XL |
| 2.8 | Duplicate records across ArXiv/Scopus/CrossRef | `[X]` fuzzy dedup with provenance | M | — |
| 2.9 | Can't tell if a paper is retracted | `[ ]` | H | S |
| 2.10 | Preprint vs peer-reviewed version confusion | `[ ]` | M | S |

## PHASE 3 — Reading and synthesis

| # | Problem | Status | Impact | Effort |
|---|---|---|---|---|
| 3.1 | Screening burden — a single systematic review takes 1000+ hours; title/abstract screening alone averages 33 days | `[~]` screener exists, single-shot | H | M |
| 3.2 | Protocol-to-publication median 25.7 months; only 71.9% of registered reviews ever publish | `[ ]` | M | L |
| 3.3 | Literature review writing — synthesis, not summary; output reads like stitched abstracts | `[~]` **your named complaint** | H | L |
| 3.4 | No structured extraction table (population/method/metric/result per paper) | `[ ]` | H | M |
| 3.5 | Can't see how a field evolved over time | `[ ]` | M | M |
| 3.6 | Contradictions across papers invisible | `[X]` dedicated agent | H | — |
| 3.7 | Research gaps not identified systematically | `[X]` dedicated agent | H | — |
| 3.8 | No PRISMA flow diagram / audit trail | `[ ]` | M | M |

## PHASE 4 — Doing the work

| # | Problem | Status | Impact | Effort |
|---|---|---|---|---|
| 4.1 | Reproducibility — >70% of researchers failed to reproduce another study's result; >50% failed their own | `[!]` | H | — |
| 4.2 | Only 16% say their institution has procedures to improve reproducibility | `[!]` | H | — |
| 4.3 | No data management plan, no code/data archiving discipline | `[ ]` | M | M |
| 4.4 | Can't find datasets/benchmarks for the topic | `[~]` topic map names datasets, no links | M | M |
| 4.5 | Stats/methods errors caught only at review | `[ ]` | M | L |
| 4.6 | Equipment/lab budget — 57.1% named insufficient research budget | `[!]` | H | — |

## PHASE 5 — Writing

| # | Problem | Status | Impact | Effort |
|---|---|---|---|---|
| 5.1 | Academic English quality — a leading global barrier, worst for non-native speakers | `[~]` humanizer only fixes AI-tone | H | M |
| 5.2 | Citation formatting churn across styles | `[X]` BibTeX/APA/IEEE/MLA | M | — |
| 5.3 | Reference list errors / broken DOIs | `[X]` validator via CrossRef | M | — |
| 5.4 | LaTeX bibliography renumbering | `[X]` | L | — |
| 5.5 | Plagiarism/self-plagiarism anxiety | `[~]` keyword-level only | M | M |
| 5.6 | AI-detection anxiety — journals now screen for LLM text | `[~]` humanizer | M | S |
| 5.7 | No journal-specific formatting (word limits, section order, figures) | `[ ]` | M | M |
| 5.8 | Cover letter / response-to-reviewer writing | `[ ]` | M | S |

## PHASE 6 — Publishing

| # | Problem | Status | Impact | Effort |
|---|---|---|---|---|
| 6.1 | **Journal choice by field only** — ignores SCI/SCIE, Scopus, Q1–Q4, CiteScore, APC, decision time | `[~]` **your named complaint**; 108-journal list + LLM guess | H | M |
| 6.2 | Predatory journals — many falsely claim Scopus indexing; Beall's List frozen since Jan 2017 | `[ ]` | H | M |
| 6.3 | Clone/hijacked journals impersonating real ones | `[ ]` | H | M |
| 6.4 | UGC-CARE compliance — mandatory for Indian promotion, not checkable in-app | `[ ]` | H | M |
| 6.5 | APCs unaffordable — high APCs are the most-cited OA barrier (88 papers in a 2004–2023 scoping review); AAAS survey confirms widespread inability to pay | `[ ]` show APC + waiver eligibility | H | M |
| 6.6 | Desk rejection after weeks of waiting — scope mismatch | `[ ]` scope-fit scoring | H | M |
| 6.7 | Turnaround time unknown before submitting | `[ ]` | M | M |
| 6.8 | Peer review slow and inconsistent — 30.5% of Indian researchers named insufficient peer review a cause of the reproducibility crisis | `[!]` | H | — |
| 6.9 | Simultaneous-submission rules and withdrawal etiquette unknown | `[ ]` | L | S |

## PHASE 7 — Funding

| # | Problem | Status | Impact | Effort |
|---|---|---|---|---|
| 7.1 | Funding decline — 69% in North America report reduced funding; budgets top concern for 60% of research offices, 58% of researchers | `[!]` | H | — |
| 7.2 | Doesn't know which grants exist or when they close | `[~]` `/funders` page, static | H | M |
| 7.3 | Grant writing skill absent | `[~]` grant writer agent | H | M |
| 7.4 | Research-office engagement is the #1 cited problem in winning funding (57%) | `[!]` | H | — |

## PHASE 8 — Career and after publication

| # | Problem | Status | Impact | Effort |
|---|---|---|---|---|
| 8.1 | Publish-or-perish pressure — 62% call it the leading cause of the reproducibility crisis | `[!]` | H | — |
| 8.2 | Can't track own citations/h-index across sources | `[ ]` | M | S |
| 8.3 | No collaborator discovery | `[ ]` | H | M |
| 8.4 | Reviewer invitations unmatched to expertise | `[ ]` | L | M |
| 8.5 | Admin + teaching load crowds out research | `[!]` | H | — |
| 8.6 | Early-career attrition pressure | `[!]` | H | — |

**Count:** 56 problems. `[X]` solved 8 · `[~]` partial 13 · `[ ]` buildable 24 · `[!]` out of scope 11.

The 24 `[ ]` items are the roadmap. The 11 `[!]` items belong in the README as
stated non-goals so scope stays honest.

---

## THE FOUR BIG BUILDS

### Build A — Access Router (problems 1.5, 2.1–2.4, 2.9)

Highest real-world value; no "AI research agent" competitor does it.

Given a DOI, cascade until the user has the PDF:

1. **OpenAlex** `best_oa_location` → OA status, licence, PDF URL
2. **Unpaywall** DOI API — 30M+ articles, 50,000+ sources; requires a contact email per request
3. **arXiv / PMC / CORE** — preprint or accepted manuscript
4. **Institutional check** — user picks their institution once; store its OpenURL
   link-resolver base URL + EZproxy prefix, then generate the resolver link.
   LibKey/Third Iron runs this exact waterfall commercially (OA version of record
   → subscription → aggregator → OA non-version-of-record); it is reproducible
   with free sources
5. **Who has access** — OpenAlex institution + affiliation data shows which
   institutions publish in that journal → "ask a co-author here"
6. **Fallback** — auto-draft an author-request email (author contact from
   CrossRef/OpenAlex) plus an ILL request

Flag retractions here too (Retraction Watch data sits in CrossRef).

Non-negotiable: legal sources only. No Sci-Hub or shadow libraries — that makes
the app unusable by any institution and legally toxic.

### Build B — Journal Fit v2 (problems 6.1–6.7)

Current agent is the weak link: 108 verified journals, then an **LLM guesses the
quartile**, then a relative-IF estimate. An LLM guessing Q1 vs Q2 is a
hallucination surface on the number that decides someone's promotion.

Replace with real data:

| Source | Gives | Cost |
|---|---|---|
| Scimago SJR CSV export | ~30k journals: ISSN, SJR, **SJR Best Quartile**, H-index, category, publisher, OA flag | Free, non-commercial with citation |
| Scopus Source List (Elsevier XLSX) | Active/discontinued coverage, CiteScore, ASJC codes | Free |
| DOAJ API | Vetted OA journals, APC amounts, licence, review process | Free |
| UGC-CARE list | India promotion compliance | Scrape/manual |
| Beall's List (archived) + Retraction Watch | Predatory/clone red flags — Beall frozen at Jan 2017, one signal only, never alone | Free |
| OpenAlex venue stats | Publication volume, topic distribution, acceptance-adjacent signals | Free |

Output card per journal: **quartile (verified, with year + category)**, SJR,
CiteScore, indexing badges (SCIE / SSCI / Scopus / DOAJ / UGC-CARE), APC + waiver,
scope-fit score against the actual abstract, median time to first decision,
predatory risk flag with the reason.

Filter and sort by quartile, index, APC ceiling, decision speed — not just field.

### Build C — Research Starter (problems 1.1–1.8, 5.1)

Makes the app usable by the 50% non-researching faculty, cold.

- Guided intake: department → interest → what you already teach → 3 candidate
  topics scored on novelty × data availability × feasibility for a first paper
- "Your first 30 days" checklist per topic, each step linked to the in-app tool
  that does it
- Inline explainers: what a DOI is, what Q1 means, what a preprint is, what peer
  review does
- Worked example: one topic taken end-to-end through every tool, viewable as a demo

This is the differentiator — every other AI research tool assumes an already
competent researcher.

### Build D — Literature Builder v2 (problems 3.1–3.5, 3.8)

Current version clusters claims then asks an LLM per paragraph, so output reads
as stitched abstracts — the complaint. Change the unit of work from *paragraph*
to *evidence table*:

1. Structured extraction per paper: population, method, dataset, metric, result,
   limitation → an editable table
2. Synthesis matrix: methods × datasets × findings, showing agreement, conflict,
   and blank cells (blank cells are gaps — reuse the gap agent)
3. Narrative generated **from the table**, so every sentence traces to a cell
4. Every claim carries an inline citation key; unsupported sentence = build error
5. Export: PRISMA flow diagram, evidence table CSV, `.tex` with `\cite{}` intact

---

## PERFORMANCE + UI ("not fast, no loading animation")

Root cause, found not guessed: `app.py:378` `/research` calls
`future.result(timeout=300)` — the browser holds one HTTP request open up to
**5 minutes** with zero output. Same synchronous pattern on
`/generate-literature`, `/check-plagiarism`, `/recommend-journals`,
`/run-benchmark`. Only `templates/plagiarism.html:172` fakes progress with a
rotating-message `setInterval`. No `EventSource`, no polling, anywhere.

Fixes in order:

1. **Job queue + streaming progress.** `POST /research` returns `job_id`
   immediately; a worker thread writes stage events; `GET /events/<job_id>`
   streams Server-Sent Events. The pipeline already has 8 named stages — emit one
   event each. The perceived-speed problem dies before real speed improves.
2. **Real speed.** Discovery already runs its 3 API searches concurrently
   (`enhanced_paper_discovery_agent.py:131`, `asyncio.gather`), so the remaining
   wins are caching by DOI in the existing `MemoryStore`, batching LLM calls, and
   caching the topic map so re-runs are instant.
3. **Skeleton + stage UI.** Per-stage cards filling in as events arrive, running
   paper counter, `prefers-reduced-motion` guards.
4. **Cancel button.** A 5-minute run with no cancel is the worst part of the UX.
5. **Live cost/token meter** — `results.usage` already carries the numbers.

## PRECISION ("not precise")

- Journal quartiles: LLM guess → verified dataset (Build B). Biggest single win.
- Claim extraction: require a verbatim evidence sentence that actually appears in
  the abstract; drop claims failing the check.
- Contradiction: the TF-IDF prefilter + Likert judge is sound; report agreement
  across 3 repeats at temperature 0 rather than one run — provider
  nondeterminism is already a documented limitation.
- Provenance tag on every number in the UI: `verified` / `estimated` /
  `LLM-inferred`. The recommender already has `quartile_source` — make that
  pattern global and visible.

---

## BUILD ORDER

| Wave | Ships | Why first |
|---|---|---|
| **1** | SSE job queue + skeleton UI + cancel; concurrent discovery + DOI cache | Fixes the blocking complaint; no new data dependencies |
| **2** | Journal Fit v2 (Scimago CSV + Scopus list + DOAJ + UGC-CARE + predatory flags) | Kills the worst hallucination surface; `M` effort, `H` impact |
| **3** | Access Router (OpenAlex → Unpaywall → CORE/arXiv → institutional resolver → author request) | The real-world problem nobody else solves; strongest moat |
| **4** | Literature Builder v2 (evidence table → synthesis → PRISMA export) | Highest effort, needs waves 1–3 stable |
| **5** | Research Starter onboarding + worked example | Best once the tools it links to are solid |

Waves 2 and 3 are independent — parallelizable.

---

## SKILLS TO INSTALL

Already in your ECC set; mapped to the waves above.

| Skill | Used for |
|---|---|
| `ecc:frontend-patterns` + `ecc:motion-ui` | Wave 1 — loading states, skeletons, reduced-motion |
| `ecc:api-design` | Wave 1 — job/SSE endpoint contract |
| `ecc:redis-patterns` | Wave 1 — job queue when in-process threads stop being enough |
| `ecc:python-patterns` + `ecc:python-testing` | All waves — 63KB `app.py` needs a blueprint split |
| `ecc:cost-aware-llm-pipeline` | Waves 2, 4 — batching, caching, cost ceilings |
| `ecc:iterative-retrieval` | Waves 3, 4 — multi-round retrieval instead of one-shot |
| `ecc:eval-harness` + `ecc:benchmark` | Prove each wave improved precision instead of guessing |
| `ecc:dashboard-builder` | Evidence tables, synthesis matrix UI |
| `ecc:security-review` | Before any auth/institution-credential work in Build A |
| `ecc:scientific-thinking-literature-review` | Wave 4 — synthesis quality rubric |

Project-level: split `app.py` (63KB, 34 routes) into Flask blueprints before
wave 2. Every wave touches it; it is already the bottleneck.

---

## Sources

- [Clarivate — Research Offices of the Future 2025](https://clarivate.com/academia-government/blog/research-offices-of-the-future-key-findings-from-the-2025-report/)
- [Elsevier — Researcher of the Future / Confidence in Research](https://www.elsevier.com/insights/confidence-in-research/researcher-of-the-future)
- [Hurdles to open access publishing faced by authors: scoping review 2004–2023 (PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12365406/)
- [AAAS — Many Researchers Face Difficulties Paying Open Access Fees](https://www.aaas.org/news/aaas-survey-many-researchers-face-difficulties-paying-open-access-fees)
- [Difficult Terrains of Research Publications Faced by Researchers (PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11329867/)
- [Barriers perceived by researchers in an evolving medical college, Madhya Pradesh (PubMed)](https://pubmed.ncbi.nlm.nih.gov/35360799/)
- [Mentoring Faculty in Indian Academia — Manu Awasthi](https://manu-awasthi.medium.com/mentoring-faculty-in-indian-academia-12f34048c730)
- [Digital Tools to Support the Systematic Review Process (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12035789/)
- [Research Screener: ML tool to semi-automate abstract screening (Systematic Reviews)](https://link.springer.com/article/10.1186/s13643-021-01635-3)
- [Biomedical researchers' perspectives on reproducibility (PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11537370/)
- [Reproducibility and replicability: what 452 professors think, USA and India (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11940819/)
- [OpenAlex blog — Introducing Unpaywall](https://blog.openalex.org/unpaywall/)
- [Unpaywall OA-status database and API — CASRAI](https://casrai.org/guides/unpaywall-open-access-status-database-api)
- [LibKey Link Technical FAQ — Third Iron](https://support.thirdiron.com/support/solutions/articles/72000570248-libkey-link-technical-faq)
- [LibKey Discovery — OCLC Support](https://help.oclc.org/Discovery_and_Reference/WorldCat_Discovery/Search_results/LibKey_Discovery_search_results)
- [SCImago Journal Rank — journal list with CSV download](https://www.scimagojr.com/journalrank.php)
- [Beall's List (archived)](https://beallslist.net/)
- [Predatory publishing practices: what researchers should know — UKSG Insights](https://insights.uksg.org/articles/10.1629/uksg.631)
