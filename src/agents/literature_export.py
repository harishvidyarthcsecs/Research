"""
Literature export helpers: evidence-table CSV and .tex document generation.

document_to_latex() builds the same skeleton the client-side JS in
templates/literature_builder.html used to build (see downloadLiterature('latex')),
but server-side, from the full section content — including the new
evidence_synthesis section — and covers all sections/bibliography rather than
whatever the browser happened to have in memory.

The result is piped through latex_citation_reorder.reorder_citations() (unmodified,
pre-existing module) so \\bibitem order always matches citation order in the export.
"""
import csv
import io
from typing import Any, Dict, List

from ..models.data_models import EvidenceRow
from .latex_citation_reorder import reorder_citations

_CSV_FIELDS = [
    "paper_id", "bibitem_key", "population", "method", "dataset",
    "metric", "result", "limitation", "extraction_source", "confidence",
]


def evidence_table_to_csv(rows: List[EvidenceRow]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: getattr(row, field) for field in _CSV_FIELDS})
    return buf.getvalue()


def document_to_latex(document_dict: Dict[str, Any]) -> str:
    """document_dict is the JSON-serialized LiteratureDocument (outline/sections/
    bibliography), the same shape the API already returns to the browser."""
    outline_title = document_dict.get("outline", {}).get("title", "Literature Review")

    parts = [
        "\\documentclass{article}\n\\usepackage{cite}\n\\begin{document}\n",
        f"\\title{{{outline_title}}}\n\\maketitle\n\n",
    ]
    for section in document_dict.get("sections", []):
        parts.append(f"\\section{{{section.get('title', '')}}}\n{section.get('content', '')}\n\n")

    parts.append("\\begin{thebibliography}{99}\n")
    for entry in document_dict.get("bibliography", []):
        parts.append(f"{entry}\n")
    parts.append("\\end{thebibliography}\n\\end{document}")

    latex_source = "".join(parts)
    reordered, _info = reorder_citations(latex_source)
    return reordered
