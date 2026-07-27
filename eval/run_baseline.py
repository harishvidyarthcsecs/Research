"""
Naive single-LLM baseline: one prompt per topic containing all frozen
abstracts, asking for claims, contradictions, and gaps in a single shot.
Scored with the same matchers as the pipeline for a fair comparison.

Usage:
    python -m eval.run_baseline
    python -m eval.run_baseline --topics slug1,slug2
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from eval import matching  # noqa: E402,F401
from eval.run_eval import (  # noqa: E402
    TOPICS_DIR, RESULTS_DIR, load_json, evaluate_topic,
    write_summary, write_failure_modes,
)

MAX_ABSTRACT_CHARS = 700
MAX_PROMPT_PAPERS = 30


def build_prompt(topic: str, papers: list) -> str:
    paper_blocks = []
    for i, paper in enumerate(papers[:MAX_PROMPT_PAPERS]):
        abstract = (paper.get("abstract") or "")[:MAX_ABSTRACT_CHARS]
        paper_blocks.append(
            f"[{i + 1}] {paper.get('title')} ({paper.get('year')})\n{abstract}")

    return (
        f"You are reviewing the literature on: {topic}\n\n"
        "Below are numbered paper abstracts. Do three things:\n"
        "1. Extract the key scientific claims (statement + which paper).\n"
        "2. Identify contradictions between claims from DIFFERENT papers.\n"
        "3. Identify research gaps. Allowed gap_type values: methodological, "
        "dataset, unexplored_subtopic, evaluation, contradiction_driven.\n\n"
        "Return ONLY a JSON object:\n"
        "{\n"
        '  "claims": [{"paper": <int>, "statement": "..."}],\n'
        '  "contradictions": [{"paper_1": <int>, "claim_1": "...", '
        '"paper_2": <int>, "claim_2": "...", "explanation": "..."}],\n'
        '  "gaps": [{"description": "...", "gap_type": "..."}]\n'
        "}\n\n"
        "Papers:\n\n" + "\n\n".join(paper_blocks)
    )


def parse_response(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def to_predictions(parsed: dict, papers: list, usage: dict) -> dict:
    def paper_id(index) -> str:
        try:
            return papers[int(index) - 1]["paper_id"]
        except (ValueError, TypeError, IndexError, KeyError):
            return f"unknown_{index}"

    return {
        "claims": [
            {"paper_id": paper_id(c.get("paper")),
             "statement": c.get("statement", "")}
            for c in parsed.get("claims", [])
        ],
        "contradictions": [
            {"paper1_id": paper_id(c.get("paper_1")),
             "paper2_id": paper_id(c.get("paper_2")),
             "claim_text_1": c.get("claim_1", ""),
             "claim_text_2": c.get("claim_2", ""),
             "explanation": c.get("explanation", ""),
             "detection_method": "baseline"}
            for c in parsed.get("contradictions", [])
        ],
        "gaps": [
            {"description": g.get("description", ""),
             "gap_type": g.get("gap_type", ""),
             "detection_method": "baseline"}
            for g in parsed.get("gaps", [])
        ],
        "usage": usage,
        "run_metadata": {"system": "naive_single_llm_baseline"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", default=None)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    from src.agents import llm_client

    selected = args.topics.split(",") if args.topics else None
    topic_dirs = [d for d in sorted(TOPICS_DIR.iterdir())
                  if d.is_dir() and (d / "papers.json").exists()
                  and (selected is None or d.name in selected)]
    if not topic_dirs:
        print("No topics with papers.json found. Run eval.snapshot_topic first.")
        sys.exit(1)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_baseline"
    run_dir = RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    per_topic = {}
    for topic_dir in topic_dirs:
        slug = topic_dir.name
        topic_info = load_json(topic_dir / "topic.json", {"topic": slug})
        papers = load_json(topic_dir / "papers.json", [])
        print(f"=== {slug}: {topic_info['topic']} (baseline) ===")

        tracker = llm_client.UsageTracker()
        prompt = build_prompt(topic_info["topic"], papers)
        try:
            raw = llm_client.chat(prompt, max_tokens=4000, temperature=0.0,
                                  tracker=tracker, purpose="baseline")
            parsed = parse_response(raw)
        except Exception as e:
            tracker.record_parse_failure("baseline")
            print(f"  Baseline call/parse failed for {slug}: {e}")
            parsed = {"claims": [], "contradictions": [], "gaps": []}

        predictions = to_predictions(parsed, papers, tracker.summary())
        metrics = evaluate_topic(topic_dir, predictions, args.k)

        out_dir = run_dir / slug
        out_dir.mkdir(exist_ok=True)
        (out_dir / "predictions.json").write_text(
            json.dumps(predictions, indent=2, default=str))
        (out_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2, default=str))
        per_topic[slug] = {"metrics": metrics}
        print(json.dumps(metrics.get("cost", {}), indent=2))

    write_summary(run_dir, per_topic, "baseline")
    write_failure_modes(run_dir, per_topic)
    print(f"\nResults written to {run_dir}")


if __name__ == "__main__":
    main()
