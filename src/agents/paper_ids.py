"""
Single canonical paper-ID function.

Wave 4 (evidence extraction, citation join) needs Claim.paper_id, EvidenceRow.paper_id,
and citation-formatter records to agree on the same ID for the same paper. Before this
module existed, claim_extraction_agent.py and custom_citation_formatter.py each computed
paper IDs slightly differently (different word counts, different regex), which silently
broke any join between claims and citations. This is the version claim_extraction_agent.py
already used, since every ID persisted in data/memory/*.json was produced by it.
"""
import re

from ..models.data_models import PaperMetadata


def paper_id_for(paper: PaperMetadata) -> str:
    if paper.doi:
        return paper.doi.replace("/", "_").replace(".", "_")
    if paper.arxiv_id:
        return f"arxiv_{paper.arxiv_id}"
    words = re.findall(r"\w+", paper.title.lower())[:5]
    return f"{'_'.join(words)}_{paper.year}"
