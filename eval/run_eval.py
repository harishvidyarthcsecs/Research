"""
Run the full research pipeline against frozen topic corpora and score its
claim extraction, contradiction detection, and gap detection against gold
annotations.

Usage:
    python -m eval.run_eval                       # all topics, LLM mode
    python -m eval.run_eval --mode pattern        # rule-based ablation
    python -m eval.run_eval --mode scored         # matched scored-grounding ablation
    python -m eval.run_eval --topics slug1,slug2  # subset

Modes:
    llm      research pipeline in LLM mode; evidence-grounded synthesis with the
             build-time citation gate ("reject").
    pattern  research pipeline with rule-based extraction fallbacks; gate on.
    scored   research pipeline in LLM mode, but the evidence-grounded synthesis
             sub-pipeline KEEPS unverifiable evidence rows and narrative
             sentences (with a grounding score / verified flag) instead of
             rejecting them. This is the ablation the paper contrasts against
             "reject" on otherwise identical decomposition and LLM calls.

Writes eval/results/<run_id>/:
    <slug>/predictions.json   raw pipeline outputs, incl. a "narrative" block
    <slug>/metrics.json       per-topic scores, incl. "downstream_errors"
    summary.json / summary.md aggregate table (adds: unsupported sentences in
                              narrative, retained FP contradictions, narrative
                              build failed)
    failure_modes.md          missed golds, FPs on known negatives, narrative
                              gate outcome
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


def run_literature(results, grounding_mode: str) -> dict:
    """Run the evidence-grounded synthesis sub-pipeline on the same research
    results and report the verify-or-reject gate's downstream effect.

    reject mode: an unsupported sentence raises UnsupportedSentenceError and the
    build fails (build_failed=True; unsupported_sentences=0 by construction).
    scored mode: unsupported sentences are kept with verified=False and counted.
    Any other failure is recorded in "error" without aborting the eval run.
    """
    from src.agents.literature_builder_agent import LiteratureBuilderAgent
    from src.agents.narrative_verifier import UnsupportedSentenceError

    empty = {
        "grounding_mode": grounding_mode, "build_failed": False, "error": None,
        "total_sentences": 0, "unsupported_sentences": 0,
        "evidence_rows": 0, "evidence_rows_no_verbatim": 0, "sentences": [],
    }
    agent = LiteratureBuilderAgent(grounding_mode=grounding_mode)
    try:
        doc = asyncio.run(agent.process(results))
    except UnsupportedSentenceError as e:
        return {**empty, "build_failed": True, "error": str(e)}
    except Exception as e:  # noqa: BLE001 - record, don't crash the eval run
        return {**empty, "error": f"{type(e).__name__}: {e}"}

    sents = [s for sec in doc.sections for s in (sec.sentences or [])]
    rows = doc.evidence_table or []
    return {
        "grounding_mode": grounding_mode,
        "build_failed": False,
        "error": None,
        "total_sentences": len(sents),
        "unsupported_sentences": sum(1 for s in sents if not s.verified),
        "evidence_rows": len(rows),
        "evidence_rows_no_verbatim": sum(1 for r in rows if not r.verbatim_evidence),
        "sentences": [
            {"text": s.text, "verified": bool(s.verified),
             "cite_keys": list(s.cite_keys)}
            for s in sents
        ],
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

    # ---- downstream-error metrics (verify-or-reject vs scored grounding) ----
    narr = predictions.get("narrative") or {}
    con = metrics.get("contradictions", {})
    metrics["downstream_errors"] = {
        "unsupported_sentences_in_narrative": (
            0 if narr.get("build_failed") else int(narr.get("unsupported_sentences", 0))),
        "retained_fp_contradictions": (
            len(con.get("false_positives_on_negatives", [])) if con else 0),
        "narrative_build_failed": bool(narr.get("build_failed")),
        "narrative_total_sentences": int(narr.get("total_sentences", 0)),
        "evidence_rows_no_verbatim": int(narr.get("evidence_rows_no_verbatim", 0)),
        "narrative_error": narr.get("error"),
    }

    gold_narrative = load_json(topic_dir / "gold_narrative.json", [])
    if gold_narrative and narr.get("sentences"):
        metrics["narrative"] = matching.match_narrative(
            narr["sentences"], gold_narrative)

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
        de = metrics.get("downstream_errors", {})
        if de.get("narrative_build_failed"):
            lines.append(f"- Narrative build FAILED (reject gate fired): "
                         f"{de.get('narrative_error', '')}")
        elif de.get("unsupported_sentences_in_narrative"):
            lines.append(f"- {de['unsupported_sentences_in_narrative']} unsupported "
                         f"sentence(s) reached the final narrative (scored grounding)")
        elif de.get("narrative_error"):
            lines.append(f"- Narrative build error: {de['narrative_error']}")
        lines.append("")
    (run_dir / "failure_modes.md").write_text("\n".join(lines))


def summary_rows(per_topic: dict) -> list:
    rows = []
    for slug, data in per_topic.items():
        metrics = data["metrics"]
        claims = metrics.get("claims", {})
        con = metrics.get("contradictions", {}).get("pair_level", {})
        gaps = metrics.get("gaps", {})
        cost = metrics.get("cost", {})
        de = metrics.get("downstream_errors", {})
        rows.append({
            "topic": slug,
            "claim_f1": claims.get("f1"),
            "con_precision": con.get("precision_on_labeled"),
            "con_recall": con.get("recall"),
            "con_fp_rate_neg": con.get("false_positive_rate_on_negatives"),
            "gap_p_at_3": gaps.get("precision_at_3"),
            "gap_recall": gaps.get("recall"),
            "unsup_sents": de.get("unsupported_sentences_in_narrative"),
            "retained_fp_contra": de.get("retained_fp_contradictions"),
            "nar_build_fail": de.get("narrative_build_failed"),
            "cost_usd": cost.get("estimated_cost_usd"),
            "parse_failures": cost.get("parse_failures"),
        })
    return rows


def write_summary(run_dir: Path, per_topic: dict, mode: str) -> None:
    rows = summary_rows(per_topic)

    (run_dir / "summary.json").write_text(json.dumps({
        "mode": mode,
        "generated_at": datetime.now().isoformat(),
        "topics": rows,
    }, indent=2))

    header = ("| topic | claim F1 | contra P (labeled) | contra R | "
              "FP rate (neg) | gap P@3 | gap R | unsup sents | "
              "retained FP contra | narrative build fail | cost $ | parse fails |")
    sep = "|" + "---|" * 12
    lines = [f"# Eval summary — mode: {mode}", "", header, sep]

    def fmt(value):
        if isinstance(value, bool):
            return "yes" if value else "no"
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
            fmt(row["unsup_sents"]), fmt(row["retained_fp_contra"]),
            fmt(row["nar_build_fail"]),
            fmt(row["cost_usd"]), fmt(row["parse_failures"]),
        ]) + " |")
    (run_dir / "summary.md").write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", default=None,
                        help="comma-separated slugs (default: all)")
    parser.add_argument("--mode", choices=["llm", "pattern", "scored"], default="llm",
                        help="pattern = rule-based ablation; "
                             "scored = matched scored-grounding ablation")
    parser.add_argument("--k", type=int, default=5, help="k for precision@k")
    args = parser.parse_args()

    if args.mode == "pattern":
        os.environ["CONTRADICTION_MODE"] = "pattern"
        os.environ["GAP_MODE"] = "rules"

    grounding = "scored" if args.mode == "scored" else "reject"

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
        predictions["narrative"] = run_literature(results, grounding)
        metrics = evaluate_topic(topic_dir, predictions, args.k)

        out_dir = run_dir / slug
        out_dir.mkdir(exist_ok=True)
        (out_dir / "predictions.json").write_text(
            json.dumps(predictions, indent=2, default=str))
        (out_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2, default=str))
        per_topic[slug] = {"metrics": metrics}
        print(json.dumps(metrics.get("cost", {}), indent=2))
        print(json.dumps(metrics.get("downstream_errors", {}), indent=2))

    write_summary(run_dir, per_topic, args.mode)
    write_failure_modes(run_dir, per_topic)
    print(f"\nResults written to {run_dir}")


if __name__ == "__main__":
    main()
