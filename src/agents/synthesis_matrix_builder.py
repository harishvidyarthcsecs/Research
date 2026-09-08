"""
Synthesis Matrix Builder.

Builds a methods x datasets grid from the evidence table. Deliberately rules-only
(no LLM call) — agreement/conflict classification must be deterministic and free,
since it runs on every (method, dataset) pair, not once per document.

Blank cells (no evidence row for a given method/dataset pair) are the gaps;
ResearchGapDetectionAgent.detect_matrix_gaps() turns them into ResearchGap objects.
"""
import re
from typing import List, Optional

from ..models.data_models import EvidenceRow, MatrixCell, SynthesisMatrix

_POSITIVE = {"improve", "improves", "improved", "outperform", "outperforms", "increase",
             "increases", "superior", "state-of-the-art", "sota", "better", "higher", "gain", "gains"}
_NEGATIVE = {"decrease", "decreases", "underperform", "underperforms", "lower", "worse",
             "fail", "fails", "limited", "drop", "drops", "degrade", "degrades"}


class SynthesisMatrixBuilder:
    """Builds the methods x datasets synthesis matrix from an evidence table."""

    def build_grid(self, rows: List[EvidenceRow]) -> SynthesisMatrix:
        methods = sorted({r.method for r in rows if r.method})
        datasets = sorted({r.dataset for r in rows if r.dataset})

        cells: List[MatrixCell] = []
        for method in methods:
            for dataset in datasets:
                cell_rows = [r for r in rows if r.method == method and r.dataset == dataset]
                cells.append(self._classify_cell(method, dataset, cell_rows))

        return SynthesisMatrix(methods=methods, datasets=datasets, cells=cells)

    def _classify_cell(self, method: str, dataset: str, cell_rows: List[EvidenceRow]) -> MatrixCell:
        if not cell_rows:
            return MatrixCell(method=method, dataset=dataset, status="blank")

        if len(cell_rows) == 1:
            r = cell_rows[0]
            cite = f" \\cite{{{r.bibitem_key}}}" if r.bibitem_key else ""
            return MatrixCell(
                method=method, dataset=dataset, row_ids=[r.id], status="single",
                summary=f"{r.result or 'A result was reported'}{cite}.",
            )

        sentiments = {self._sentiment(r.result) for r in cell_rows}
        sentiments.discard(None)
        status = "agreement" if len(sentiments) <= 1 else "conflict"
        keys = [r.bibitem_key for r in cell_rows if r.bibitem_key]
        cite = f" \\cite{{{','.join(keys)}}}" if keys else ""
        if status == "agreement":
            summary = f"{len(cell_rows)} studies agree{cite}."
        else:
            summary = f"{len(cell_rows)} studies report conflicting outcomes{cite}."

        return MatrixCell(
            method=method, dataset=dataset,
            row_ids=[r.id for r in cell_rows], status=status, summary=summary,
        )

    def _sentiment(self, result: Optional[str]) -> Optional[str]:
        if not result:
            return None
        words = set(re.findall(r"[a-z-]+", result.lower()))
        if words & _POSITIVE:
            return "positive"
        if words & _NEGATIVE:
            return "negative"
        return None
