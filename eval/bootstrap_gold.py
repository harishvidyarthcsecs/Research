"""
Auto-draft candidate gold annotations from real pipeline output, for a human
to correct instead of writing gold data from scratch.

This does NOT produce validated ground truth. Every item is tagged
"status": "REVIEW_NEEDED" and written to *_draft.json files, separate from the
real gold_*.json files eval/run_eval.py scores against. A human must review,
correct, and copy the accepted items into gold_claims.json /
gold_contradictions.json / gold_gaps.json before a topic counts toward the
benchmark (see eval/README.md workflow step 2).

Usage:
    python -m eval.snapshot_topic "graph neural networks drug discovery" --slug gnn-drug
    python -m eval.bootstrap_gold gnn-drug

Produces eval/topics/<slug>/:
    gold_claims_draft.json          claims pre-filled from the pipeline run
    gold_contradictions_draft.json  candidate positives (high Likert score)
                                     and candidate negatives (low Likert score)
    gold_gaps_draft.json            detected gaps, for confirm/edit/reject
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from eval.run_eval import TOPICS_DIR, load_json, build_frozen_papers, predictions_from_results  # noqa: E402

# Likert scale: 1 = strong support ... 11 = strong contradiction (see
# ContradictionDetectionAgent). Candidates outside this band are ambiguous
# and left out of both buckets rather than guessed.
POSITIVE_LIKERT_MIN = 8
NEGATIVE_LIKERT_MAX = 3


def _draft_claims(claims: list) -> list:
    return [
        {
            "paper_id": c["paper_id"],
            "statement": c["statement"],
            "status": "REVIEW_NEEDED",
        }
        for c in claims
    ]


def _draft_contradictions(contradictions: list) -> dict:
    positives, negatives = [], []
    for c in contradictions:
        likert = c.get("likert_score")
        if likert is None:
            continue
        entry = {
            "paper_id_1": c.get("paper1_id"),
            "claim_text_1": c.get("evidence_claim1", ""),
            "paper_id_2": c.get("paper2_id"),
            "claim_text_2": c.get("evidence_claim2", ""),
            "label": "contradiction" if likert >= POSITIVE_LIKERT_MIN else "no_contradiction",
            "notes": f"auto-drafted from pipeline output (likert_score={likert}): "
                     f"{c.get('explanation', '')}",
            "status": "REVIEW_NEEDED",
        }
        if likert >= POSITIVE_LIKERT_MIN:
            positives.append(entry)
        elif likert <= NEGATIVE_LIKERT_MAX:
            negatives.append(entry)
        # mid-range scores are ambiguous; leave out of both buckets
    return {"positives": positives, "negatives": negatives}


def _draft_gaps(gaps: list) -> list:
    return [
        {
            "description": g["description"],
            "gap_type": g["gap_type"],
            "keywords": [],
            "status": "REVIEW_NEEDED",
        }
        for g in gaps
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="topic slug under eval/topics/ (from snapshot_topic)")
    args = parser.parse_args()

    topic_dir = TOPICS_DIR / args.slug
    papers_payload = load_json(topic_dir / "papers.json", None)
    if papers_payload is None:
        print(f"No frozen corpus at {topic_dir}/papers.json. "
              f"Run eval.snapshot_topic first.")
        sys.exit(1)
    topic_info = load_json(topic_dir / "topic.json", {"topic": args.slug})

    from src.research_system import AutonomousResearchSystem

    print(f"Running pipeline against frozen corpus for: {topic_info['topic']}")
    frozen = build_frozen_papers(papers_payload)
    system = AutonomousResearchSystem()
    results = asyncio.run(system.research(topic_info["topic"], papers=frozen))
    predictions = predictions_from_results(results)

    drafts = {
        "gold_claims_draft.json": _draft_claims(predictions["claims"]),
        "gold_contradictions_draft.json": _draft_contradictions(predictions["contradictions"]),
        "gold_gaps_draft.json": _draft_gaps(predictions["gaps"]),
    }
    for name, content in drafts.items():
        (topic_dir / name).write_text(json.dumps(content, indent=2))

    n_claims = len(drafts["gold_claims_draft.json"])
    n_pos = len(drafts["gold_contradictions_draft.json"]["positives"])
    n_neg = len(drafts["gold_contradictions_draft.json"]["negatives"])
    n_gaps = len(drafts["gold_gaps_draft.json"])
    print(f"Drafted {n_claims} claims, {n_pos} candidate contradiction positives, "
          f"{n_neg} candidate negatives, {n_gaps} candidate gaps — all REVIEW_NEEDED.")
    print(f"Review each *_draft.json in {topic_dir}, correct/reject entries, "
          f"then copy accepted items (without the status field) into "
          f"gold_claims.json / gold_contradictions.json / gold_gaps.json.")


if __name__ == "__main__":
    main()
