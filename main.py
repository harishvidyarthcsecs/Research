"""Command-line entry point for the Autonomous Research Agent System."""
import asyncio
import json
import sys
from pathlib import Path

from src.reporting.report_builder import build_report_dict, render_markdown
from src.research_system import AutonomousResearchSystem


DEFAULT_TOPIC = "Use of Graph Neural Networks in Drug Discovery"


def _parse_args(argv):
    flags = {arg for arg in argv if arg.startswith("--")}
    unknown = flags - {"--markdown", "--report", "--json-only"}
    if unknown:
        raise ValueError(f"Unknown flag(s): {', '.join(sorted(unknown))}")
    topic = " ".join(arg for arg in argv if not arg.startswith("--")).strip()
    return topic or DEFAULT_TOPIC, bool(flags & {"--markdown", "--report"}), "--json-only" in flags


async def main(argv=None):
    """Run research and write the canonical JSON/optional Markdown reports."""
    topic, write_markdown, json_only = _parse_args(sys.argv[1:] if argv is None else argv)
    system = AutonomousResearchSystem()

    if not json_only:
        print(f"Starting autonomous research on: {topic}")

    results = await system.research(topic)
    report = build_report_dict(results)

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "research_results.json"
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, default=str)

    if write_markdown:
        markdown_path = output_dir / "research_results.md"
        with open(markdown_path, "w", encoding="utf-8") as handle:
            handle.write(render_markdown(report))

    if not json_only:
        print("\n" + (report["executive_summary"] or "No executive summary was generated."))
        summary = report["summary"]
        print(
            f"Papers: {summary['papers_analyzed']} | Claims: {summary['claims_extracted']} | "
            f"Contradictions: {summary['contradictions_found']} | "
            f"Gaps: {summary['research_gaps_identified']}"
        )
        for recommendation in report["recommendations"][:3]:
            print(
                f"#{recommendation.get('rank', '-')} "
                f"[{float(recommendation.get('priority') or 0):.0%}] "
                f"{recommendation.get('title', '')}"
            )
        print(f"JSON report: {json_path}")
        if write_markdown:
            print(f"Markdown report: {output_dir / 'research_results.md'}")


if __name__ == "__main__":
    asyncio.run(main())
