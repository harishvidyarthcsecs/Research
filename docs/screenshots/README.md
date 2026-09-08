# Screenshots — feature walkthrough

Captured 2026-09-08 against `python run.py` (`http://localhost:5001`), Groq
`openai/gpt-oss-120b` as the LLM provider, viewport 1440×900.

| # | Screen | File | What it shows |
|---|---|---|---|
| 1 | Research console (home) | `01-home.png` | Topic box, year/format/venue filters, tool grid, research-history panel. |
| 2 | Journal Fit Recommender | `02-journal-fit.png` | Abstract-in form + research-field hint; empty state. |
| 3 | Reference Validator | `03-reference-validator.png` | Paste/upload a bibliography; per-reference CrossRef/OpenAlex check + reformat. |
| 4 | Enhanced Citations | `04-enhanced-citations.png` | Citation generator/formatter (APA / IEEE / MLA / BibTeX / custom). |
| 5 | AI Writing Humanizer | `05-humanizer.png` | Paste text or a PDF; removes AI-writing patterns. |
| 6 | LaTeX Citation Reorder | `06-latex-reorder.png` | Upload a `.tex`; renumber `\cite` keys into order of appearance. |
| 7 | Similarity Checker | `07-plagiarism.png` | Paste ≥30 words; OpenAlex/CrossRef/S2 similarity report. |
| 8 | Paper Access Router | `08-access-router.png` | DOI/title → legal open-access routes (OA PDF, preprint, repo, ILL). |
| 9 | Citation Network | `09-citation-network.png` | Paper title/ID + depth → D3 citing/cited graph (OpenAlex). |
| 10 | Abstract Screener | `10-abstract-screener.png` | Bulk abstracts + inclusion/exclusion criteria → include/exclude decisions. |
| 11 | Pre-Submission Checklist | `11-checklist.png` | Manuscript type / journal / field → tailored submission checklist. |
| 12 | Grant Writer | `12-grant-writer.png` | Project details + funder template (NSF/NIH/ERC…) → draft sections. |
| 13 | Benchmark dashboard | `13-benchmark.png` | Dedicated pipeline vs naive single-LLM baseline on a frozen eval topic. |
| 14 | Literature Builder | `14-literature-builder.png` | Topic → structured multi-section review with verified citations + export. |
| 15 | Research run — progress | `15-research-progress.png` | Live 9-stage progress tracker while a research job streams. |
| 16 | Research run — results | `16-research-results.png` | Executive-summary card, stat tiles, LLM-usage bar, export buttons (incl. **Download report .md**), 9 stages complete. |
| 17 | Research run — Recommendations tab | `17-recommendations-tab.png` | 8 ranked AI recommendations grouped by category (experiment / next-step / reading) with priority %, concrete action, and supporting evidence. |
| 18 | Journal Fit — results | `18-journal-fit-results.png` | Ranked journals with fit score, SJR quartile + provenance, CiteScore, APC, Scimago + journal-website links, per-journal submission tip. *(Field auto-detection mis-fired on the VoRG abstract — see the paper review, item I-8.)* |
| 19 | Journal Database — list | `19-journal-database.png` | 62,901-journal SPA: search, publisher / APC / quartile / OA filters, paginated cards. |
| 20 | Journal Database — detail | `20-journal-detail.png` | Per-journal modal: SCImago / Scopus / DOAJ / APC blocks, confidence tiers, discrepancy notes, **Visit journal website** link, "Not applicable / Not reported" where data is genuinely absent. |

Screenshots 16–17 and 20 were captured by rendering a completed run's saved result into the
live UI; the pipeline, API, and every render path are exercised exactly as in normal use.
