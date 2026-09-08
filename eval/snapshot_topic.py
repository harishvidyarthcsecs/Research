"""
Freeze a paper corpus for one evaluation topic and export pipeline-extracted
claims to a CSV so gold annotations can be authored by correction instead of
from scratch.

Usage:
    python -m eval.snapshot_topic "graph neural networks drug discovery" \
        --slug gnn-drug-discovery
    python -m eval.snapshot_topic "..." --slug ... --no-backfill

Produces eval/topics/<slug>/:
    topic.json               {"topic", "slug", "created_at", "notes",
                              "abstract_coverage", "abstract_backfill"}
    papers.json              frozen corpus (with pipeline paper_id per paper);
                             abstracts backfilled from Semantic Scholar / OpenAlex
                             when the discovery merge left them empty
    _raw/                    cached raw API responses used for backfill
    claims_to_annotate.csv   paper_id, statement, confidence, keep, corrected_statement
    gold_claims.json         empty template (fill in per eval/README.md)
    gold_contradictions.json empty template
    gold_gaps.json           empty template
    gold_narrative.json      empty template — sentences that SHOULD survive the
                             citation gate: [{"text": "<verbatim sentence>"}]
"""
import argparse
import asyncio
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from src.research_system import AutonomousResearchSystem  # noqa: E402
from src.agents.claim_extraction_agent import ClaimExtractionAgent  # noqa: E402

TOPICS_DIR = Path(__file__).resolve().parent / "topics"

_USER_AGENT = "research-agent-eval/1.0 (mailto:harishvidyarth.n.2024.csecs@rajalakshmi.edu.in)"
_HTTP_PAUSE_S = 1.0  # polite rate limit for the free S2 / OpenAlex endpoints


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


# --------------------------------------------------------------------- #
# Abstract backfill                                                     #
# --------------------------------------------------------------------- #

def _http_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed hosts
        return json.loads(resp.read().decode("utf-8", "replace"))


def _openalex_reconstruct(inverted_index: dict) -> str:
    if not inverted_index:
        return ""
    positions = []
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(word for _, word in positions).strip()


def _fetch_openalex(doi: str, cache_dir: Path):
    doi = (doi or "").strip().lower().replace("https://doi.org/", "")
    if not doi:
        return None
    cache = cache_dir / f"openalex_{slugify(doi)}.json"
    try:
        if cache.exists():
            data = json.loads(cache.read_text())
        else:
            # OpenAlex accepts the DOI with raw slashes after https://doi.org/;
            # url-encoding the slash breaks the lookup.
            data = _http_json(f"https://api.openalex.org/works/https://doi.org/{doi}")
            cache.write_text(json.dumps(data, indent=2))
    except Exception:
        return None
    return _openalex_reconstruct(data.get("abstract_inverted_index") or {}) or None


def _fetch_s2(doi: str, title: str, cache_dir: Path):
    key = doi.strip() if doi else (title or "")[:80]
    if not key:
        return None
    cache = cache_dir / f"s2_{slugify(key)}.json"
    try:
        if cache.exists():
            data = json.loads(cache.read_text())
        elif doi:
            data = _http_json(
                f"https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi.strip())}"
                "?fields=abstract,title")
        else:
            q = urllib.parse.quote(title)
            hit = _http_json(
                f"https://api.semanticscholar.org/graph/v1/paper/search?query={q}&limit=1&fields=abstract,title")
            data = (hit.get("data") or [{}])[0]
        if not cache.exists():
            cache.write_text(json.dumps(data, indent=2))
    except Exception:
        return None
    abstract = (data or {}).get("abstract")
    return abstract.strip() if abstract and abstract.strip() else None


def backfill_abstracts(papers_payload: list, topic_dir: Path) -> dict:
    """Fill empty abstracts in place from Semantic Scholar then OpenAlex.
    Returns a summary dict; also prints coverage."""
    cache_dir = topic_dir / "_raw"
    cache_dir.mkdir(parents=True, exist_ok=True)

    total = len(papers_payload)
    had = sum(1 for p in papers_payload if (p.get("abstract") or "").strip())
    filled_s2 = filled_oa = 0

    for p in papers_payload:
        if (p.get("abstract") or "").strip():
            continue
        doi = p.get("doi") or ""
        title = p.get("title") or ""
        abs_text = _fetch_s2(doi, title, cache_dir)
        src = "s2"
        if not abs_text:
            abs_text = _fetch_openalex(doi, cache_dir)
            src = "openalex"
        if abs_text:
            p["abstract"] = abs_text
            if src == "s2":
                filled_s2 += 1
            else:
                filled_oa += 1
        time.sleep(_HTTP_PAUSE_S)

    now_have = sum(1 for p in papers_payload if (p.get("abstract") or "").strip())
    coverage = now_have / total if total else 0.0
    summary = {
        "papers": total,
        "had_abstract_before": had,
        "filled_semantic_scholar": filled_s2,
        "filled_openalex": filled_oa,
        "have_abstract_after": now_have,
        "coverage": round(coverage, 3),
    }
    print(f"  abstract_coverage = {now_have}/{total} "
          f"(+{filled_s2} S2, +{filled_oa} OpenAlex)")
    return summary


# --------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic")
    parser.add_argument("--slug", default=None)
    parser.add_argument("--notes", default="")
    parser.add_argument("--no-backfill", action="store_true",
                        help="skip Semantic Scholar / OpenAlex abstract backfill")
    args = parser.parse_args()

    slug = args.slug or slugify(args.topic)
    topic_dir = TOPICS_DIR / slug
    topic_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running pipeline once to snapshot papers for: {args.topic}")
    system = AutonomousResearchSystem()
    results = asyncio.run(system.research(args.topic))

    id_gen = ClaimExtractionAgent()
    papers_payload = []
    for paper in results.papers:
        record = json.loads(paper.json())
        record["paper_id"] = id_gen._generate_paper_id(paper)
        papers_payload.append(record)

    backfill_summary = {"skipped": True}
    if not args.no_backfill:
        backfill_summary = backfill_abstracts(papers_payload, topic_dir)

    if backfill_summary.get("skipped"):
        with_abs = sum(1 for p in papers_payload if (p.get("abstract") or "").strip())
        coverage = round(with_abs / len(papers_payload), 3) if papers_payload else 0.0
    else:
        coverage = backfill_summary.get("coverage")

    (topic_dir / "topic.json").write_text(json.dumps({
        "topic": args.topic,
        "slug": slug,
        "created_at": datetime.now().isoformat(),
        "notes": args.notes,
        "abstract_coverage": coverage,
        "abstract_backfill": backfill_summary,
    }, indent=2))
    (topic_dir / "papers.json").write_text(json.dumps(papers_payload, indent=2))

    with open(topic_dir / "claims_to_annotate.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["paper_id", "statement", "confidence",
                         "keep (y/n)", "corrected_statement"])
        for claim in results.claims:
            writer.writerow([claim.paper_id, claim.statement,
                             claim.confidence, "", ""])

    for name, template in [
        ("gold_claims.json", []),
        ("gold_contradictions.json", {"positives": [], "negatives": []}),
        ("gold_gaps.json", []),
        ("gold_narrative.json", []),
    ]:
        path = topic_dir / name
        if not path.exists():
            path.write_text(json.dumps(template, indent=2))

    print(f"Snapshot written to {topic_dir}")
    print(f"  papers: {len(papers_payload)}, claims to annotate: {len(results.claims)}")
    print("Next: annotate claims_to_annotate.csv and fill the gold_*.json files "
          "(schemas in eval/README.md).")


if __name__ == "__main__":
    main()
