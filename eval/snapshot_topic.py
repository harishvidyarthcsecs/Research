"""
Freeze a paper corpus for one evaluation topic and export pipeline-extracted
claims to a CSV so gold annotations can be authored by correction instead of
from scratch.

Usage:
    python -m eval.snapshot_topic "graph neural networks drug discovery" \
        --slug gnn-drug-discovery

Produces eval/topics/<slug>/:
    topic.json               {"topic", "slug", "created_at", "notes"}
    papers.json              frozen corpus (with pipeline paper_id per paper)
    claims_to_annotate.csv   paper_id, statement, confidence, keep, corrected_statement
    gold_claims.json         empty template (fill in per eval/README.md)
    gold_contradictions.json empty template
    gold_gaps.json           empty template
"""
import argparse
import asyncio
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from src.research_system import AutonomousResearchSystem  # noqa: E402
from src.agents.claim_extraction_agent import ClaimExtractionAgent  # noqa: E402

TOPICS_DIR = Path(__file__).resolve().parent / "topics"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic")
    parser.add_argument("--slug", default=None)
    parser.add_argument("--notes", default="")
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

    (topic_dir / "topic.json").write_text(json.dumps({
        "topic": args.topic,
        "slug": slug,
        "created_at": datetime.now().isoformat(),
        "notes": args.notes,
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
