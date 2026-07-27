"""
Run the full research pipeline against frozen topic corpora and score its
claim extraction, contradiction detection, and gap detection against gold
annotations.

Usage:
    python -m eval.run_eval                       # all topics, LLM mode
    python -m eval.run_eval --mode pattern        # rule-based ablation
    python -m eval.run_eval --topics slug1,slug2  # subset

Writes eval/results/<run_id>/:
    <slug>/predictions.json   raw pipeline outputs
    <slug>/metrics.json       per-topic scores
    summary.json / summary.md aggregate table (incl. cost + parse failures)
    failure_modes.md          missed golds and FPs on known negatives
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from eval import matching  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
TOPICS_DIR = EVAL_DIR / "topics"
RESULTS_DIR = EVAL_DIR / "results"


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def build_frozen_papers(papers_payload):
    from src.models.data_models import PaperMetadata
    papers = []
    for record in papers_payload:
        data = {k: v for k, v in record.items() if k != "paper_id"}
        papers.append(PaperMetadata(**data))
    return papers


def predictions_from_results(results) -> dict:
    return {
        "claims": [
            {"paper_id": c.paper_id, "statement": c.statement,
             "confidence": c.confidence}
            for c in results.claims
        ],
        "contradictions": [
            {"paper1_id": c.paper1_id, "paper2_id": c.paper2_id,
             "claim1_id": c.claim1_id, "claim2_id": c.claim2_id,
             "evidence_claim1": c.evidence_claim1,
             "evidence_claim2": c.evidence_claim2,
             "likert_score": c.likert_score,
             "explanation": c.explanation,
             "detection_method": c.detection_method}
            for c in results.contradictions
        ],
        "gaps": [
            {"description": g.description, "gap_type": g.gap_type,
             "rank": g.rank, "priority": g.priority,
             "evidence": g.evidence,
             "detection_method": g.detection_method}
            for g in sorted(results.research_gaps,
                            key=lambda g: g.rank or 999)
        ],
        "usage": results.usage,
        "run_metadata": results.run_metadata,
    }


def evaluate_topic(topic_dir: Path, predictions: dict, k: int) -> dict:
    metrics = {}
    gold_claims = load_json(topic_dir / "gold_claims.json", [])
    if gold_claims:
        # Claims may be annotated with corrected_statement; prefer it
        gold = [{"paper_id": g["paper_id"],
                 "statement": g.get("corrected_statement") or g["statement"]}
                for g in gold_claims]
        metrics["claims"] = matching.match_claims(predictions["claims"], gold)

    gold_contradictions = load_json(topic_dir / "gold_contradictions.json",
                                    {"positives": [], "negatives": []})
    if gold_contradictions.get("positives") or gold_contradictions.get("negatives"):
        metrics["contradictions"] = matching.match_contradictions(
            predictions["contradictions"], gold_contradictions)

    gold_gaps = load_json(topic_dir / "gold_gaps.json", [])
    if gold_gaps:
        metrics["gaps"] = matching.match_gaps(
            predictions["gaps"], gold_gaps, ks=(3, k))

    metrics["cost"] = {
        "estimated_cost_usd": predictions["usage"].get("estimated_cost_usd", 0),
        "llm_calls": predictions["usage"].get("calls", 0),
        "parse_failures": predictions["usage"].get("parse_failures", 0),
    }
    return metrics


def write_failure_modes(run_dir: Path, per_topic: dict) -> None:
    lines = ["# Failure modes", ""]
    for slug, data in per_topic.items():
        metrics = data["metrics"]
        lines.append(f"## {slug}")
        con = metrics.get("contradictions")
        if con:
            for fp in con.get("false_positives_on_negatives", []):
                lines.append(f"- FP on known-negative pair "
                             f"{fp.get('paper1_id')} / {fp.get('paper2_id')}: "
                             f"{fp.get('explanation', '')}")
            for miss in con.get("missed_gold", []):
                lines.append(f"- Missed gold contradiction "
                             f"{miss.get('paper_id_1')} / {miss.get('paper_id_2')}: "
                             f"{miss.get('notes', '')}")
        claims = metrics.get("claims")
        if claims and claims.get("missed_gold_indices"):
            lines.append(f"- Missed {len(claims['missed_gold_indices'])} gold claims")
        gaps = metrics.get("gaps")
        if gaps and gaps.get("missed_gold_indices"):
            lines.append(f"- Missed gold gaps: indices {gaps['missed_gold_indices']}")
        lines.append("")
    (run_dir / "failure_modes.md").write_text("\n".join(lines))


def write_summary(run_dir: Path, per_topic: dict, mode: str) -> None:
    rows = []
    for slug, data in per_topic.items():
        metrics = data["metrics"]
        claims = metrics.get("claims", {})
        con = metrics.get("contradictions", {}).get("pair_level", {})
        gaps = metrics.get("gaps", {})
        cost = metrics.get("cost", {})

        rows.append({
            "topic": slug,
            "claim_f1": claims.get("f1"),
            "con_precision": con.get("precision_on_labeled"),
            "con_recall": con.get("recall"),
            "con_fp_rate_neg": con.get("false_positive_rate_on_negatives"),
            "gap_p_at_3": gaps.get("precision_at_3"),
            "gap_recall": gaps.get("recall"),
            "cost_usd": cost.get("estimated_cost_usd"),
            "parse_failures": cost.get("parse_failures"),
        })

    (run_dir / "summary.json").write_text(json.dumps({
        "mode": mode,
        "generated_at": datetime.now().isoformat(),
        "topics": rows,
    }, indent=2))

    header = ("| topic | claim F1 | contra P (labeled) | contra R | "
              "FP rate (neg) | gap P@3 | gap R | cost $ | parse fails |")
    sep = "|" + "---|" * 9
    lines = [f"# Eval summary — mode: {mode}", "", header, sep]

    def fmt(value):
        if isinstance(value, float):
            return f"{value:.3f}"
        if isinstance(value, int):
            return str(value)
        return "-"

    for row in rows:
        lines.append("| " + " | ".join([
            row["topic"], fmt(row["claim_f1"]), fmt(row["con_precision"]),
            fmt(row["con_recall"]), fmt(row["con_fp_rate_neg"]),
            fmt(row["gap_p_at_3"]), fmt(row["gap_recall"]),
            fmt(row["cost_usd"]), fmt(row["parse_failures"]),
        ]) + " |")
    (run_dir / "summary.md").write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", default=None,
                        help="comma-separated slugs (default: all)")
    parser.add_argument("--mode", choices=["llm", "pattern"], default="llm",
                        help="pattern = rule-based ablation")
    parser.add_argument("--k", type=int, default=5, help="k for precision@k")
    args = parser.parse_args()

    if args.mode == "pattern":
        os.environ["CONTRADICTION_MODE"] = "pattern"
        os.environ["GAP_MODE"] = "rules"

    from src.research_system import AutonomousResearchSystem

    selected = args.topics.split(",") if args.topics else None
    topic_dirs = [d for d in sorted(TOPICS_DIR.iterdir())
                  if d.is_dir() and (d / "papers.json").exists()
                  and (selected is None or d.name in selected)]
    if not topic_dirs:
        print("No topics with papers.json found. Run eval.snapshot_topic first.")
        sys.exit(1)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{args.mode}"
    run_dir = RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    per_topic = {}
    for topic_dir in topic_dirs:
        slug = topic_dir.name
        topic_info = load_json(topic_dir / "topic.json", {"topic": slug})
        print(f"=== {slug}: {topic_info['topic']} ({args.mode}) ===")

        papers_payload = load_json(topic_dir / "papers.json", [])
        frozen = build_frozen_papers(papers_payload)

        system = AutonomousResearchSystem()
        results = asyncio.run(system.research(topic_info["topic"], papers=frozen))
        predictions = predictions_from_results(results)
        metrics = evaluate_topic(topic_dir, predictions, args.k)

        out_dir = run_dir / slug
        out_dir.mkdir(exist_ok=True)
        (out_dir / "predictions.json").write_text(
            json.dumps(predictions, indent=2, default=str))
        (out_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2, default=str))
        per_topic[slug] = {"metrics": metrics}
        print(json.dumps(metrics.get("cost", {}), indent=2))

    write_summary(run_dir, per_topic, args.mode)
    write_failure_modes(run_dir, per_topic)
    print(f"\nResults written to {run_dir}")


if __name__ == "__main__":
    main()
