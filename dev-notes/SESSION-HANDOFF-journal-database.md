# Session Handoff — Enterprise Journal Database

Written 2026-08-18. Read this before touching `src/db/`, `scripts/etl/`,
`src/blueprints/journals.py`, or `frontend-journals/` again.

---

## Problem statement (verbatim from the user)

> Update this research agent in a way that it tracks the all the Journal
> List from https://cfr.annauniv.edu/research/academics/journals-list.php
> and stores in the data base with the help of this and the ISSN Number
> track all the data from Scopus, http://scimagojr.com/,
> https://mjl.clarivate.com/home take all the parameters possible and
> also need to track their APC Status and also about the Discounted
> APC/Waiver we can use the help of DOAJ but the data present there is a
> bit old, we need to cross check on it... Use SQL instead of excel...
> Plan on this perfectly each and everything should be authenticated
> from the original website and need not be hallucinated. Develop this
> on enterprise level and show me the workflow.

The app previously resolved journal quartile/APC data from three flat
JSON files (`src/data/*.json`), no SQL database anywhere in the repo.

## What was actually built

A SQL-backed (SQLite via SQLAlchemy, Alembic-migrated), multi-source,
provenance-tracked journal database:

- **Schema** (`src/db/models.py`): `journals` (canonical row) plus
  one table per source — `journal_scimago`, `journal_scopus`,
  `journal_mjl`, `journal_doaj`, `journal_annauniv_cfr`,
  `journal_publisher_apc`, `country_income_classification`,
  `publisher_waiver_policy`, `journal_apc_consolidated`,
  `journal_risk_flags`, `journal_identifiers`, `etl_run_log`. Every
  source-table row carries its own `source_url`/`snapshot_date` so
  provenance is a column, not a guess.
- **ETL** (`scripts/etl/`): one ingest script per source, each
  idempotent (upsert by normalized ISSN via a shared `IssnIndex`
  helper), each logging into `etl_run_log`. `reconcile.py` merges
  everything into the canonical `journals` table, consolidates APC
  figures, computes advisory waiver eligibility, and flags predatory-
  publisher risk.
- **API** (`src/blueprints/journals.py`): `GET /api/journals` (search/
  filter/paginate), `GET /api/journals/<issn>` (full detail),
  `GET /api/journals/facets`, `GET /api/admin/etl/status`,
  `POST /api/admin/etl/run/<source>`.
- **Frontend** (`frontend-journals/`): Vite + React 19 + TypeScript +
  Tailwind, replicating `github.com/mohamedaaris/OpportunityHub`'s
  component tree and glassmorphism design (that repo is itself a
  re-skinned journal directory — its `event.ts` field-name comments map
  straight back to journal terms). Served by Flask at `/journals`.
- **Existing recommender kept working**: `src/agents/journal_metadata.py`
  was swapped from flat-JSON `lru_cache` reads to SQL queries against
  this DB, same function signatures — `/journal-fit` is unaffected.

### Real per-source access findings — the actual hard part

Every source turned out to need a different access pattern. This is the
knowledge worth preserving, not just "it's done":

| Source | Access pattern | Notes |
|---|---|---|
| Anna University CFR | Automated HTML scrape | TLS chain is broken server-side; scoped verify-fallback for this one host only |
| DOAJ | CSV baseline + live API cross-check | `doaj.org/api/search/journals/issn:{issn}` is live, no auth |
| SCImago | Manual CSV | Cloudflare Turnstile challenge — `cloudscraper`/`curl_cffi` both tested live and failed |
| Elsevier APC | Bulk XLSX, no login | `legacyfileshare.elsevier.com/els_com_pricing/article-publishing-charge.xlsx` |
| Wiley APC | 2× bulk XLSX, no login | fully-OA + hybrid lists, `authors.wiley.com` |
| Springer APC | **No bulk file exists** | confirmed live via their own FAQ — per-journal only; their 72-country waiver list *is* bulk and was captured |
| IEEE APC | Bulk PDF, no login | no ISSN column at all — matched by normalized title, ~178/223 matched honestly |
| Frontiers APC | Category price table (bulk) + per-journal (on-demand) | no ISSN on either page |
| ACM APC | `cloudscraper` gets through | flat rate, not per-journal — $1800 list / $1300 member |
| MDPI / OUP / PLOS | Blocked | `cloudscraper` still 403s all three — logged honestly as `partial`/failed, not faked |
| Taylor & Francis / SAGE | No bulk file | on-demand per-journal only, not wired into bulk `run_all.py` |
| Scopus Source List | **Manual XLSX, real file now ingested** | scopus.com itself is Cloudflare-blocked; the official `ext_list_*.xlsx` has no CiteScore/Percentile at all (Elsevier ships that separately) |
| Clarivate MJL | **Manual CSV only** | confirmed a "public" search API exists (`/api/jprof/public/rank-search`) but requires an `x-1p-session` token generated client-side by the Angular app's own JS — not obtainable via plain HTTP, real dead end |
| World Bank income | Live API, no auth | authoritative source for the country-tier the publisher waiver policies are actually keyed to |

## How it was solved — including the messy part

Two Claude Code sessions ended up building this exact plan **in
parallel, unknowingly**. One session (this one) did the research and
planning, then started implementing the schema/ETL. Partway through, a
second session named `enterprise-journal-database` was discovered
running in the background for 19 hours, already mid-edit on the same
files. The two sessions coordinated directly (cross-session messages),
compared state, and the user chose to defer to the more-advanced
session as source of truth.

Division of labor that resulted:
- **`enterprise-journal-database` session**: built the schema, all ETL
  scripts, the Flask blueprint, the `journal_metadata.py` swap, and the
  React frontend — all live-tested against real sources.
- **This session**: did the original research/planning, then a
  read-only verification pass (test suite, live API checks,
  `.gitignore`/README coverage) once the other session reported
  feature-complete, and found + reported the scope of a real bug (see
  below). Later, when the user supplied a real downloaded Scopus file
  and an MJL share-link, this session fixed two real issues in
  `ingest_scopus_source_list.py` (CiteScore/percentile don't exist in
  that file; a fragile column-match) and ran it against the real
  48,888-row file, plus did the MJL public-API investigation that
  confirmed a genuine dead end — both landed with the other session's
  explicit go-ahead once it became blocked by a local environment issue.

This is documented plainly because a future session picking this repo
back up needs to know two agents can silently duplicate work on the
same task, and that coordinating rather than overwriting is what made
this land cleanly instead of corrupting the shared SQLite file.

## Verified vs. not (as of the last `run_all.py` pass)

| Source | Status | Fetched | Upserted | Failed |
|---|---|---|---|---|
| Anna University CFR | success | 12,202 | 12,202 | 0 |
| DOAJ CSV baseline | success | 23,183 | 23,183 | 0 |
| DOAJ live cross-check | success | 200 | 200 | 0 |
| SCImago | success | 31,086 | 31,086 | 0 |
| Elsevier APC | success | 3,215 | 3,215 | 0 |
| Wiley APC (fully-OA) | success | 604 | 604 | 0 |
| Wiley APC (hybrid) | success | 1,266 | 1,266 | 0 |
| IEEE APC | partial | 223 | 178 | 45 (title-match misses) |
| Frontiers APC | success | 5 | 5 | 0 (starter slug list only) |
| ACM APC | success | 31 | 31 | 0 |
| MDPI / OUP / PLOS | partial | 0 | 0 | 1 each (Cloudflare-blocked) |
| World Bank income | partial | 295 | 217 | 78 (regional aggregates, not countries) |
| Publisher waiver policy seed | success | 6 | 6 | 0 |
| Scopus Source List | success | 48,805 | 48,805 | 0 |
| **Reconcile (final)** | success | **62,901** | **62,901** | 0 |

**Not populated**: Clarivate MJL (needs the user's free WoS account CSV
export, dropped at `data/incoming/mjl_export.csv`), Taylor & Francis /
SAGE (on-demand only, no bulk job), MDPI/OUP/PLOS (Cloudflare-blocked).
Every one of these is logged honestly in `etl_run_log`, not silently
skipped or faked.

## Known open bug (unresolved as of this doc)

`GET /`, `GET /journals`, and `GET /journal-fit` all return HTTP 500:

```
PermissionError: [Errno 1] Operation not permitted: '.../templates/index.html'
```

Confirmed this is scoped to Flask's `render_template`/
`send_from_directory` (file-open at request time) — every pure-JSON
`/api/journals/*` route works fine, and the SQLite DB reads are
unaffected. This affects the pre-existing homepage too, not just the
new journals feature — it is an environment/sandbox-level issue on
whichever machine/process is serving the app, not a code bug introduced
by this work. Not fixed by either session yet.

## Where the rest of the detail lives

- Full approved implementation plan: `~/.claude/plans/update-this-research-agent-soft-wall.md`
- Notion log entries (dated 2026-08-17 and 2026-08-18) under the
  "Research Agent – Gap & Contradiction Detection" project page.
- `README.md` → "Journal Database" section for the source-citation table
  end users see.
