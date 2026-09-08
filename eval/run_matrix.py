"""
Run the evaluation over a matrix of (topic x mode x repeat) and aggregate.

Each cell is executed as its own subprocess (process isolation between runs, so
no LLM-client or env state leaks across repeats), reusing the frozen corpora, so
there is no paper-source API traffic.

Usage:
    python -m eval.run_matrix --topics gnn-drug-discovery,dl-malware-detection \
        --modes llm,pattern,scored,baseline --repeats 5

Writes eval/results/matrix_<UTC>/:
    runs.json      every child run_dir + its mode/repeat
    aggregate.md   per-mode tables: per-topic mean +/- SD and a pooled row, for
                   claim P/R/F1, contradiction FP rate, gap recall + P@3, the
                   three downstream-error metrics, cost, parse failures.
"""
import argparse
import json
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
REPO_DIR = EVAL_DIR.parent
RESULTS_DIR = EVAL_DIR / "results"

_RUN_DIR_RE = re.compile(r"Results written to (.+)$", re.MULTILINE)

METRIC_KEYS = [
    ("claim_precision", lambda m: _g(m, "claims", "precision")),
    ("claim_recall", lambda m: _g(m, "claims", "recall")),
    ("claim_f1", lambda m: _g(m, "claims", "f1")),
    ("contra_fp_rate_neg", lambda m: _g(m, "contradictions", "pair_level",
                                        "false_positive_rate_on_negatives")),
    ("gap_recall", lambda m: _g(m, "gaps", "recall")),
    ("gap_p_at_3", lambda m: _g(m, "gaps", "precision_at_3")),
    ("unsupported_sentences_in_narrative",
     lambda m: _g(m, "downstream_errors", "unsupported_sentences_in_narrative")),
    ("retained_fp_contradictions",
     lambda m: _g(m, "downstream_errors", "retained_fp_contradictions")),
    ("narrative_build_failed",
     lambda m: 1.0 if _g(m, "downstream_errors", "narrative_build_failed") else 0.0),
    ("cost_usd", lambda m: _g(m, "cost", "estimated_cost_usd")),
    ("parse_failures", lambda m: _g(m, "cost", "parse_failures")),
]


def _g(d, *path):
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_DIR).decode().strip()
    except Exception:
        return "unknown"


def _run_once(mode: str, topics: str, k: int) -> Path:
    module = "eval.run_baseline" if mode == "baseline" else "eval.run_eval"
    cmd = [sys.executable, "-m", module, "--topics", topics, "--k", str(k)]
    if mode != "baseline":
        cmd += ["--mode", mode]
    print(f"    $ {' '.join(cmd)}")
    out = subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, text=True)
    sys.stdout.write(out.stdout[-2000:])
    if out.returncode != 0:
        sys.stderr.write(out.stderr[-4000:])
        raise RuntimeError(f"{module} ({mode}) exited {out.returncode}")
    match = _RUN_DIR_RE.search(out.stdout)
    if not match:
        raise RuntimeError(f"could not find run dir in output of {module} ({mode})")
    return Path(match.group(1).strip())


def _mean_sd(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None, None
    if len(vals) == 1:
        return vals[0], 0.0
    return statistics.mean(vals), statistics.pstdev(vals)


def _fmt(mean, sd):
    if mean is None:
        return "-"
    return f"{mean:.3f} ± {sd:.3f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", required=True, help="comma-separated slugs")
    parser.add_argument("--modes", default="llm,pattern,scored,baseline")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    topics = [t.strip() for t in args.topics.split(",") if t.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    matrix_dir = RESULTS_DIR / f"matrix_{stamp}"
    matrix_dir.mkdir(parents=True, exist_ok=True)

    # samples[mode][topic][metric_name] -> list of values across repeats
    samples = {m: {t: {k: [] for k, _ in METRIC_KEYS} for t in topics} for m in modes}
    runs_log = []

    for mode in modes:
        for r in range(args.repeats):
            print(f"[{mode}] repeat {r + 1}/{args.repeats}")
            run_dir = _run_once(mode, ",".join(topics), args.k)
            runs_log.append({"mode": mode, "repeat": r + 1, "run_dir": str(run_dir)})
            for topic in topics:
                mpath = run_dir / topic / "metrics.json"
                if not mpath.exists():
                    continue
                metrics = json.loads(mpath.read_text())
                for name, getter in METRIC_KEYS:
                    val = getter(metrics)
                    if val is not None:
                        samples[mode][topic][name].append(val)

    (matrix_dir / "runs.json").write_text(json.dumps(runs_log, indent=2))

    lines = [
        f"# Evaluation matrix — {stamp}",
        "",
        f"- commit: `{_git_hash()}`",
        f"- topics: {', '.join(topics)}",
        f"- modes: {', '.join(modes)}",
        f"- repeats per cell: {args.repeats}",
        "- values: mean ± population SD across repeats",
        "",
    ]

    for mode in modes:
        lines.append(f"## mode: {mode}")
        lines.append("")
        lines.append("| topic | " + " | ".join(k for k, _ in METRIC_KEYS) + " |")
        lines.append("|" + "---|" * (len(METRIC_KEYS) + 1))
        pooled = {k: [] for k, _ in METRIC_KEYS}
        for topic in topics:
            cells = []
            for name, _ in METRIC_KEYS:
                vals = samples[mode][topic][name]
                pooled[name].extend(vals)
                cells.append(_fmt(*_mean_sd(vals)))
            lines.append(f"| {topic} | " + " | ".join(cells) + " |")
        pooled_cells = [_fmt(*_mean_sd(pooled[name])) for name, _ in METRIC_KEYS]
        lines.append("| **pooled** | " + " | ".join(pooled_cells) + " |")
        lines.append("")

    (matrix_dir / "aggregate.md").write_text("\n".join(lines))
    print(f"\nMatrix written to {matrix_dir}")
    print((matrix_dir / "aggregate.md").read_text())


if __name__ == "__main__":
    main()
