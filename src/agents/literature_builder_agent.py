"""
Literature Builder Agent - Transforms extracted claims into structured academic literature.

This agent converts stored claims into coherent literature sections while preserving
academic tone, ensuring citation backing, and maintaining traceability.

Primary mode ("llm"): for each claim cluster with real paper abstracts, asks the
shared LLM client to synthesize one flowing academic paragraph grounded only in
the supplied abstract text, citing each source with its \\cite{bibitem_key}. This
replaces the previous fixed sentence-selection heuristic with genuine LLM
authorship while still constraining the model to the retrieved abstracts (no
free-standing generation).

Fallback mode ("rules"): the original sentence-extraction/templating pipeline,
kept as the no-API-key fallback and rule-based ablation baseline
(set LITERATURE_MODE=rules), mirroring TOPIC_MODE / CONTRADICTION_MODE / GAP_MODE.
"""

import asyncio
import json
import logging
import os
from typing import List, Dict, Any, Optional, Tuple, Callable
from collections import defaultdict
import re
from datetime import datetime

from . import llm_client
from .paper_ids import paper_id_for
from . import narrative_verifier
from .narrative_verifier import UnsupportedSentenceError
from .evidence_extraction_agent import EvidenceExtractionAgent
from .custom_citation_formatter import CustomCitationFormatter
from .synthesis_matrix_builder import SynthesisMatrixBuilder
from .research_gap_detection_agent import ResearchGapDetectionAgent

# Import requests with fallback
try:
    import requests
except ImportError:
    requests = None

# Try relative imports first, then absolute
try:
    from ..models.data_models import (
        Claim, PaperMetadata, ResearchResults, TopicMap, ClaimCluster,
        LiteratureSection, LiteratureOutline, LiteratureDocument, LiteratureFilter,
        EvidenceRow, MatrixCell, SynthesisMatrix, PrismaCounts
    )
except ImportError:
    # Fallback to absolute imports for testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from models.data_models import (
        Claim, PaperMetadata, ResearchResults, TopicMap, ClaimCluster,
        LiteratureSection, LiteratureOutline, LiteratureDocument, LiteratureFilter,
        EvidenceRow, MatrixCell, SynthesisMatrix, PrismaCounts
    )

logger = logging.getLogger(__name__)


def apply_literature_filter(research_results: ResearchResults, filt: LiteratureFilter) -> ResearchResults:
    """Apply a LiteratureFilter to a ResearchResults before the evidence/narrative
    pipeline runs. Previously LiteratureFilter was defined but never consumed —
    the UI's filter form posted data that was silently discarded."""
    q_rankings = set(filt.q_rankings)

    def _q_rank(paper: PaperMetadata) -> str:
        venue_lower = (paper.venue or "").lower()
        rankings = {
            'Q1': ['nature', 'science', 'cell', 'lancet', 'nejm', 'jama', 'pnas'],
            'Q2': ['ieee', 'acm', 'springer', 'elsevier', 'wiley'],
            'Q3': ['arxiv', 'preprint', 'workshop', 'conference'],
        }
        for rank, venues in rankings.items():
            if any(v in venue_lower for v in venues):
                return rank
        return 'Q3'

    def _is_sa(paper: PaperMetadata) -> bool:
        sa_keywords = ['systematic review', 'meta-analysis', 'literature review',
                       'survey', 'comprehensive review', 'systematic analysis']
        text = f"{paper.title} {paper.abstract}".lower()
        return any(kw in text for kw in sa_keywords)

    filtered_papers = []
    for p in research_results.papers:
        if _q_rank(p) not in q_rankings:
            continue
        if not filt.include_sa_papers and _is_sa(p):
            continue
        if filt.min_year is not None and p.year and p.year < filt.min_year:
            continue
        if filt.max_year is not None and p.year and p.year > filt.max_year:
            continue
        filtered_papers.append(p)

    surviving_ids = {paper_id_for(p) for p in filtered_papers}
    filtered_claims = [
        c for c in research_results.claims
        if c.paper_id in surviving_ids and c.confidence >= filt.min_confidence
    ]

    return research_results.model_copy(update={
        "papers": filtered_papers,
        "claims": filtered_claims,
    })

class LiteratureBuilderAgent:
    """Agent responsible for building structured academic literature from claims."""
    
    def __init__(self, mode: Optional[str] = None, memory_store=None,
                 grounding_mode: Optional[str] = None):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.mode = mode  # None = auto: "llm" if a provider is available
        # "reject" (default) = build-time citation gate: an unverifiable sentence
        # or evidence row is discarded / raises. "scored" = keep it with a
        # grounding score. A/B'd in eval/run_eval.py --mode scored.
        self.grounding_mode = grounding_mode or os.getenv("GROUNDING_MODE") or "reject"
        self.tracker: Optional[llm_client.UsageTracker] = None
        self.q_rankings = {
            'Q1': ['nature', 'science', 'cell', 'lancet', 'nejm', 'jama', 'pnas'],
            'Q2': ['ieee', 'acm', 'springer', 'elsevier', 'wiley'],
            'Q3': ['arxiv', 'preprint', 'workshop', 'conference']
        }
        self.sa_keywords = [
            'systematic review', 'meta-analysis', 'literature review',
            'survey', 'comprehensive review', 'systematic analysis'
        ]
        self.evidence_agent = EvidenceExtractionAgent(
            memory_store, mode=mode, grounding_mode=self.grounding_mode)
        self.citation_formatter = CustomCitationFormatter(memory_store)
        self.matrix_builder = SynthesisMatrixBuilder()
        self.gap_agent = ResearchGapDetectionAgent(memory_store, mode=mode)

    def _resolve_mode(self) -> str:
        mode = self.mode or os.getenv("LITERATURE_MODE")
        if mode in ("llm", "rules"):
            return mode
        return "llm" if llm_client.get_provider() is not None else "rules"

    async def process(
        self, research_results: ResearchResults,
        progress: Optional[Callable[..., None]] = None,
    ) -> LiteratureDocument:
        """
        Main processing function to build literature from research results.

        Args:
            research_results: Complete research results with claims and papers
            progress: optional callback(stage:int, name:str, state:str, **detail) for
                      SSE progress reporting; stages 10-17 continue the main research
                      pipeline's stages 1-9.

        Returns:
            LiteratureDocument: Structured academic literature, now carrying an
            evidence table, a methods x datasets synthesis matrix, and PRISMA counts
            alongside the existing outline/sections/bibliography.
        """
        def report(stage: int, name: str, state: str, **detail):
            if progress:
                progress(stage, name, state, **detail)

        mode = self._resolve_mode()
        self.logger.info(f"Starting literature building process (mode={mode})")

        try:
            report(10, "Classify Papers", "running")
            classified_papers = self._classify_papers(research_results.papers)
            report(10, "Classify Papers", "done")

            report(11, "Evidence Extraction", "running")
            evidence_rows = await self.evidence_agent.process(
                research_results.papers, research_results.claims, research_results.topic_map
            )
            report(11, "Evidence Extraction", "done", rows=len(evidence_rows))

            report(12, "Bibliography", "running")
            citation_records = await self.citation_formatter.process(research_results.papers)
            key_by_paper = {c["paper_id"]: c["bibitem_key"] for c in citation_records}
            for row in evidence_rows:
                row.bibitem_key = key_by_paper.get(row.paper_id, "")
            bibliography = [
                c["bibitem_citation"] for c in
                sorted(citation_records, key=lambda c: (c["formatted_authors"], c["year"] or 0))
            ]
            report(12, "Bibliography", "done")

            report(13, "Cluster Claims", "running")
            claim_clusters = await self._cluster_claims(
                research_results.claims,
                research_results.papers,
                research_results.contradictions,
                classified_papers
            )
            report(13, "Cluster Claims", "done")

            report(14, "Synthesis Matrix", "running")
            matrix = self.matrix_builder.build_grid(evidence_rows)
            blank_pairs = [(c.method, c.dataset) for c in matrix.cells if c.status == "blank"]
            gaps_by_cell = await self.gap_agent.detect_matrix_gaps(blank_pairs, research_results.topic_map)
            for cell in matrix.cells:
                gap = gaps_by_cell.get((cell.method, cell.dataset))
                if gap:
                    cell.gap_id = gap.id
            report(14, "Synthesis Matrix", "done", cells=len(matrix.cells), gaps=len(gaps_by_cell))

            report(15, "Outline", "running")
            outline = self._generate_outline(
                claim_clusters,
                research_results.topic_map,
                research_results.papers
            )
            report(15, "Outline", "done")

            report(16, "Narrative Generation", "running")
            rows_by_paper: Dict[str, List[EvidenceRow]] = defaultdict(list)
            for r in evidence_rows:
                rows_by_paper[r.paper_id].append(r)
            rows_by_key = {r.bibitem_key: r for r in evidence_rows if r.bibitem_key}
            sections = await self._build_sections(claim_clusters, outline, mode, rows_by_paper, rows_by_key, matrix)
            report(16, "Narrative Generation", "done")

            report(17, "PRISMA Counts", "running")
            prisma = self._build_prisma_counts(research_results, evidence_rows)
            report(17, "PRISMA Counts", "done")

            # Step: Create final document
            document = LiteratureDocument(
                outline=outline,
                sections=sections,
                bibliography=bibliography,
                evidence_table=evidence_rows,
                synthesis_matrix=matrix,
                prisma=prisma,
                metadata={
                    'total_papers': len(research_results.papers),
                    'total_claims': len(research_results.claims),
                    'q1_papers': len([p for p in classified_papers if classified_papers[p]['q_rank'] == 'Q1']),
                    'q2_papers': len([p for p in classified_papers if classified_papers[p]['q_rank'] == 'Q2']),
                    'q3_papers': len([p for p in classified_papers if classified_papers[p]['q_rank'] == 'Q3']),
                    'sa_papers': len([p for p in classified_papers if classified_papers[p]['is_sa']]),
                    'evidence_rows': len(evidence_rows),
                    'topic': research_results.topic_map.main_topic
                },
                generated_at=datetime.now()
            )

            self.logger.info(f"Literature building completed: {len(sections)} sections generated")
            return document

        except Exception as e:
            self.logger.error(f"Error in literature building: {str(e)}")
            raise e
    
    def _classify_papers(self, papers: List[PaperMetadata]) -> Dict[str, Dict[str, Any]]:
        """Classify papers by Q-ranking and SA status."""
        classified = {}
        
        for paper in papers:
            paper_id = getattr(paper, 'id', f"paper_{hash(paper.title)}")
            venue_lower = paper.venue.lower() if paper.venue else ""
            title_lower = paper.title.lower() if paper.title else ""
            abstract_lower = paper.abstract.lower() if paper.abstract else ""
            
            # Determine Q-ranking
            q_rank = 'Q3'  # Default
            for rank, venues in self.q_rankings.items():
                if any(venue in venue_lower for venue in venues):
                    q_rank = rank
                    break
            
            # Determine SA status
            is_sa = any(keyword in title_lower or keyword in abstract_lower 
                       for keyword in self.sa_keywords)
            
            classified[paper_id] = {
                'q_rank': q_rank,
                'is_sa': is_sa,
                'venue': paper.venue,
                'year': paper.year
            }
        
        return classified
    
    async def _cluster_claims(
        self, 
        claims: List[Claim], 
        papers: List[PaperMetadata],
        contradictions: List[Any],
        classified_papers: Dict[str, Dict[str, Any]]
    ) -> List[ClaimCluster]:
        """Cluster claims by themes, methods, and research objectives."""
        
        # Create paper lookup keyed by the canonical paper_id (matches Claim.paper_id).
        # NOTE: paper.id (the Pydantic default_factory field) is a random per-instance
        # timestamp, never set to match claim.paper_id at construction time anywhere in
        # the discovery agents — keying this lookup by paper.id silently produced an
        # all-None cluster.papers on every real run. paper_id_for() is the same DOI/
        # title-based function claim extraction uses to set claim.paper_id.
        paper_lookup = {paper_id_for(p): p for p in papers}
        
        # Group claims by similarity
        clusters = []
        processed_claims = set()
        
        for i, claim in enumerate(claims):
            claim_id = getattr(claim, 'id', claim.id)
            if claim_id in processed_claims:
                continue
            
            # Find similar claims
            similar_claims = [claim]
            similar_papers = [paper_lookup.get(claim.paper_id)]
            
            for j, other_claim in enumerate(claims[i+1:], i+1):
                other_claim_id = getattr(other_claim, 'id', other_claim.id)
                if other_claim_id in processed_claims:
                    continue
                
                # Check similarity based on keywords, methods, datasets
                if self._are_claims_similar(claim, other_claim):
                    similar_claims.append(other_claim)
                    similar_papers.append(paper_lookup.get(other_claim.paper_id))
                    processed_claims.add(other_claim_id)
            
            processed_claims.add(claim_id)
            
            # Create cluster
            cluster = self._create_cluster(
                similar_claims, 
                similar_papers, 
                contradictions,
                classified_papers,
                len(clusters)
            )
            clusters.append(cluster)
        
        return clusters
    
    def _are_claims_similar(self, claim1: Claim, claim2: Claim) -> bool:
        """Determine if two claims are similar enough to be clustered."""
        
        # Check for common methods
        methods1 = set(claim1.metrics.keys()) if claim1.metrics else set()
        methods2 = set(claim2.metrics.keys()) if claim2.metrics else set()
        method_overlap = len(methods1.intersection(methods2)) > 0
        
        # Check for common datasets
        datasets1 = set(claim1.datasets) if claim1.datasets else set()
        datasets2 = set(claim2.datasets) if claim2.datasets else set()
        dataset_overlap = len(datasets1.intersection(datasets2)) > 0
        
        # Check for keyword similarity in statement
        words1 = set(claim1.statement.lower().split())
        words2 = set(claim2.statement.lower().split())
        word_overlap = len(words1.intersection(words2)) / max(len(words1), len(words2), 1)
        
        return method_overlap or dataset_overlap or word_overlap > 0.3
    
    def _create_cluster(
        self, 
        claims: List[Claim], 
        papers: List[PaperMetadata],
        contradictions: List[Any],
        classified_papers: Dict[str, Dict[str, Any]],
        cluster_index: int
    ) -> ClaimCluster:
        """Create a claim cluster with metadata."""
        
        # Extract common themes
        all_words = []
        methods = set()
        datasets = set()
        
        for claim in claims:
            all_words.extend(claim.statement.lower().split())
            if claim.metrics:
                methods.update(claim.metrics.keys())
            if claim.datasets:
                datasets.update(claim.datasets)
        
        # Find most common theme
        word_freq = defaultdict(int)
        for word in all_words:
            if len(word) > 3:  # Skip short words
                word_freq[word] += 1
        
        theme = max(word_freq.items(), key=lambda x: x[1])[0] if word_freq else "general"
        
        # Determine research objective
        research_objective = self._extract_research_objective(claims)
        
        # Get Q-rankings and SA papers
        q_ranking = {}
        sa_papers = []
        
        for paper in papers:
            if paper and hasattr(paper, 'title'):
                paper_id = getattr(paper, 'id', f"paper_{hash(paper.title)}")
                if paper_id in classified_papers:
                    q_ranking[paper_id] = classified_papers[paper_id]['q_rank']
                    if classified_papers[paper_id]['is_sa']:
                        sa_papers.append(paper_id)
        
        return ClaimCluster(
            cluster_id=f"cluster_{cluster_index}",
            theme=theme.title(),
            method=list(methods)[0] if methods else None,
            dataset=list(datasets)[0] if datasets else None,
            task=self._extract_task(claims),
            research_objective=research_objective,
            claims=claims,
            papers=[p for p in papers if p is not None],
            contradictions=self._find_cluster_contradictions(claims, contradictions),
            agreements=self._find_cluster_agreements(claims),
            q_ranking=q_ranking,
            sa_papers=sa_papers
        )
    
    def _extract_research_objective(self, claims: List[Claim]) -> str:
        """Extract the main research objective from claims."""
        objectives = []
        for claim in claims:
            statement = claim.statement.lower()
            if 'improve' in statement or 'enhance' in statement:
                objectives.append('performance improvement')
            elif 'compare' in statement or 'comparison' in statement:
                objectives.append('comparative analysis')
            elif 'novel' in statement or 'new' in statement:
                objectives.append('novel approach')
            elif 'evaluate' in statement or 'assessment' in statement:
                objectives.append('evaluation')
            else:
                objectives.append('investigation')
        
        # Return most common objective
        obj_freq = defaultdict(int)
        for obj in objectives:
            obj_freq[obj] += 1
        
        return max(obj_freq.items(), key=lambda x: x[1])[0] if obj_freq else 'investigation'
    
    def _extract_task(self, claims: List[Claim]) -> Optional[str]:
        """Extract the main task from claims."""
        tasks = []
        for claim in claims:
            statement = claim.statement.lower()
            if 'classification' in statement:
                tasks.append('classification')
            elif 'prediction' in statement or 'forecasting' in statement:
                tasks.append('prediction')
            elif 'detection' in statement:
                tasks.append('detection')
            elif 'generation' in statement:
                tasks.append('generation')
            elif 'optimization' in statement:
                tasks.append('optimization')
        
        return max(set(tasks), key=tasks.count) if tasks else None
    
    def _find_cluster_contradictions(self, claims: List[Claim], contradictions: List[Any]) -> List[str]:
        """Find contradictions within the cluster."""
        cluster_contradictions = []
        claim_ids = {getattr(claim, 'id', claim.id) for claim in claims}
        
        for contradiction in contradictions:
            if hasattr(contradiction, 'claim1_id') and hasattr(contradiction, 'claim2_id'):
                if contradiction.claim1_id in claim_ids or contradiction.claim2_id in claim_ids:
                    cluster_contradictions.append(contradiction.explanation)
            elif hasattr(contradiction, 'claim_ids'):
                if any(cid in claim_ids for cid in contradiction.claim_ids):
                    cluster_contradictions.append(contradiction.explanation)
        
        return cluster_contradictions
    
    def _find_cluster_agreements(self, claims: List[Claim]) -> List[str]:
        """Find agreements within the cluster."""
        agreements = []
        
        # Simple agreement detection based on similar metrics or outcomes
        for i, claim1 in enumerate(claims):
            for claim2 in claims[i+1:]:
                if self._claims_agree(claim1, claim2):
                    agreements.append(f"Agreement on {claim1.statement[:50]}...")
        
        return agreements
    
    def _claims_agree(self, claim1: Claim, claim2: Claim) -> bool:
        """Check if two claims agree with each other."""
        # Simple heuristic: similar confidence and overlapping content
        confidence_similar = abs(claim1.confidence - claim2.confidence) < 0.2
        
        words1 = set(claim1.statement.lower().split())
        words2 = set(claim2.statement.lower().split())
        content_overlap = len(words1.intersection(words2)) / max(len(words1), len(words2), 1) > 0.5
        
        return confidence_similar and content_overlap
    
    def _generate_outline(
        self, 
        clusters: List[ClaimCluster], 
        topic_map: TopicMap,
        papers: List[PaperMetadata]
    ) -> LiteratureOutline:
        """Generate a structured outline for the literature."""
        
        years = [p.year for p in papers if p.year]
        date_range = (min(years), max(years)) if years else (2020, 2024)
        
        sections = [
            {
                'type': 'introduction',
                'title': 'Introduction',
                'description': f'Context and motivation for {topic_map.main_topic}',
                'clusters': []
            },
            {
                'type': 'related_work',
                'title': 'Related Work',
                'description': 'Review of existing approaches and methods',
                'clusters': [c.cluster_id for c in clusters]
            },
            {
                'type': 'evidence_synthesis',
                'title': 'Evidence Synthesis',
                'description': 'Agreement, conflict, and gaps across methods and datasets',
                'clusters': []
            },
            {
                'type': 'comparative_analysis',
                'title': 'Comparative Analysis',
                'description': 'Analysis of agreements and contradictions',
                'clusters': [c.cluster_id for c in clusters if c.contradictions or c.agreements]
            },
            {
                'type': 'trends',
                'title': 'Trends and Evolution',
                'description': 'Chronological and methodological evolution',
                'clusters': [c.cluster_id for c in clusters]
            }
        ]
        
        return LiteratureOutline(
            title=f"Literature Review: {topic_map.main_topic}",
            sections=sections,
            total_papers=len(papers),
            total_claims=sum(len(c.claims) for c in clusters),
            date_range=date_range
        )
    
    async def _build_sections(
        self,
        clusters: List[ClaimCluster],
        outline: LiteratureOutline,
        mode: str = "rules",
        rows_by_paper: Optional[Dict[str, List[EvidenceRow]]] = None,
        rows_by_key: Optional[Dict[str, EvidenceRow]] = None,
        matrix: Optional[SynthesisMatrix] = None,
    ) -> List[LiteratureSection]:
        """Build the actual literature sections."""

        rows_by_paper = rows_by_paper or {}
        rows_by_key = rows_by_key or {}

        sections = []
        cluster_lookup = {c.cluster_id: c for c in clusters}

        for section_info in outline.sections:
            section_type = section_info['type']

            if section_type == 'introduction':
                section = await self._build_introduction_section(clusters, outline)
            elif section_type == 'related_work':
                section = await self._build_related_work_section(
                    clusters, section_info, mode, rows_by_paper, rows_by_key)
            elif section_type == 'evidence_synthesis':
                section = self._build_evidence_synthesis_section(matrix)
            elif section_type == 'comparative_analysis':
                section = await self._build_comparative_section(clusters, section_info)
            elif section_type == 'trends':
                section = await self._build_trends_section(clusters, section_info)
            else:
                continue

            sections.append(section)

        return sections
    
    async def _build_introduction_section(
        self, 
        clusters: List[ClaimCluster], 
        outline: LiteratureOutline
    ) -> LiteratureSection:
        """Build the introduction section."""
        
        # Extract key themes and motivation
        themes = [c.theme for c in clusters]
        theme_freq = defaultdict(int)
        for theme in themes:
            theme_freq[theme] += 1
        
        main_themes = sorted(theme_freq.items(), key=lambda x: x[1], reverse=True)[:3]
        
        content = f"""
The field of {outline.title.replace('Literature Review: ', '')} has witnessed significant developments 
across multiple research directions. This literature review examines {outline.total_papers} papers 
spanning from {outline.date_range[0]} to {outline.date_range[1]}, analyzing {outline.total_claims} 
research claims to provide a comprehensive overview of the current state of knowledge.

The primary research themes identified include {', '.join([theme[0] for theme in main_themes[:-1]])} 
and {main_themes[-1][0] if main_themes else 'various approaches'}. These themes represent the core 
areas of investigation within the domain, each contributing unique perspectives and methodological 
approaches to advancing our understanding.

This review is structured to provide both breadth and depth of coverage, examining related work 
across different methodological approaches, conducting comparative analysis of conflicting findings, 
and identifying trends in the evolution of research approaches over time.
        """.strip()
        
        return LiteratureSection(
            section_type='introduction',
            title='Introduction',
            content=content,
            citations=[],
            claim_ids=[]
        )
    
    async def _build_related_work_section(
        self,
        clusters: List[ClaimCluster],
        section_info: Dict[str, Any],
        mode: str = "rules",
        rows_by_paper: Optional[Dict[str, List[EvidenceRow]]] = None,
        rows_by_key: Optional[Dict[str, EvidenceRow]] = None,
    ) -> LiteratureSection:
        """Build the related work section."""

        rows_by_paper = rows_by_paper or {}
        rows_by_key = rows_by_key or {}

        # Group clusters by method or theme
        method_groups = defaultdict(list)
        for cluster in clusters:
            key = cluster.method or cluster.theme
            method_groups[key].append(cluster)

        content_parts = []
        all_citations = []
        all_claim_ids = []
        all_sentences = []

        for method, method_clusters in method_groups.items():
            subsection_content = await self._build_method_subsection(
                method, method_clusters, mode, rows_by_paper, rows_by_key)
            content_parts.append(subsection_content['content'])
            all_citations.extend(subsection_content['citations'])
            all_claim_ids.extend(subsection_content['claim_ids'])
            all_sentences.extend(subsection_content['sentences'])

        content = "\n\n".join(content_parts)

        return LiteratureSection(
            section_type='related_work',
            title='Related Work',
            content=content,
            citations=list(set(all_citations)),
            claim_ids=all_claim_ids,
            sentences=all_sentences,
        )

    async def _build_method_subsection(
        self,
        method: str,
        clusters: List[ClaimCluster],
        mode: str = "rules",
        rows_by_paper: Optional[Dict[str, List[EvidenceRow]]] = None,
        rows_by_key: Optional[Dict[str, EvidenceRow]] = None,
    ) -> Dict[str, Any]:
        """Build a subsection for a specific method or theme."""

        rows_by_paper = rows_by_paper or {}
        rows_by_key = rows_by_key or {}

        paragraphs = []
        citations = []
        claim_ids = []
        sentences = []

        for cluster in clusters:
            paragraph, para_citations, para_claim_ids, para_sentences = \
                await self._build_cluster_paragraph_from_table(
                    cluster, mode, rows_by_paper, rows_by_key)
            paragraphs.append(paragraph)
            citations.extend(para_citations)
            claim_ids.extend(para_claim_ids)
            sentences.extend(para_sentences)

        content = f"### {method.title()}\n\n" + "\n\n".join(paragraphs)

        return {
            'content': content,
            'citations': citations,
            'claim_ids': claim_ids,
            'sentences': sentences,
        }
    
    async def _build_cluster_paragraph(
        self,
        cluster: ClaimCluster,
        mode: str = "rules"
    ) -> Tuple[str, List[str], List[str]]:
        """Build literature from actual paper abstracts with LaTeX citations."""
        
        # Sort papers by Q-ranking and year (Q1 first, then by year descending)
        def sort_key(paper):
            paper_id = getattr(paper, 'id', f"paper_{hash(paper.title)}")
            q_rank = cluster.q_ranking.get(paper_id, 'Q3')
            q_priority = {'Q1': 1, 'Q2': 2, 'Q3': 3}.get(q_rank, 3)
            return (q_priority, -(paper.year if paper.year else 0))
        
        sorted_papers = sorted(cluster.papers, key=sort_key)
        
        # Generate bibitem keys and collect abstracts
        citations = []
        bibitem_keys = []
        abstracts_data = []
        
        for paper in sorted_papers:
            paper_id = getattr(paper, 'id', f"paper_{hash(paper.title)}")
            q_rank = cluster.q_ranking.get(paper_id, 'Q3')
            is_sa = paper_id in cluster.sa_papers
            
            # Generate bibitem key (first 2 letters of max 3 authors + year)
            bibitem_key = self._generate_bibitem_key(paper)
            bibitem_keys.append(bibitem_key)
            
            # Store abstract and paper data for substantial abstracts only
            if paper.abstract and len(paper.abstract.strip()) > 100:  # Require substantial abstracts
                abstracts_data.append({
                    'abstract': paper.abstract,
                    'bibitem_key': bibitem_key,
                    'paper': paper,
                    'q_rank': q_rank,
                    'is_sa': is_sa
                })
            
            # Build citation for reference list
            authors_str = paper.authors[0] if paper.authors else 'Unknown'
            if len(paper.authors) > 1:
                authors_str += ' et al.'
            
            citation = f"{authors_str} ({paper.year})"
            if is_sa:
                citation += " [SA]"
            citation += f" [{q_rank}]"
            citations.append(citation)
        
        # Construct literature content from actual abstracts
        content_parts = []
        
        llm_paragraph = None
        if abstracts_data and mode == "llm":
            llm_paragraph = self._llm_synthesize_paragraph(cluster, abstracts_data[:5])

        if llm_paragraph:
            content_parts.append(llm_paragraph)
        elif abstracts_data:
            # Create thematic introduction
            theme_intro = f"Research in {cluster.theme.lower()} has focused on {cluster.research_objective}. "
            content_parts.append(theme_intro)

            # Process abstracts to create coherent literature (limit to top 5 papers)
            for i, abstract_info in enumerate(abstracts_data[:5]):
                abstract_text = abstract_info['abstract']
                bibitem_key = abstract_info['bibitem_key']
                q_rank = abstract_info['q_rank']
                is_sa = abstract_info['is_sa']
                
                # Debug: Log abstract processing
                self.logger.info(f"Processing abstract {i+1}/{len(abstracts_data[:5])}: {len(abstract_text)} chars")
                
                # Process abstract into literature content with LaTeX citations
                processed_content = self._process_abstract_for_literature(abstract_text, bibitem_key)
                if processed_content:
                    # Add quality indicators for high-impact papers
                    if q_rank == 'Q1':
                        processed_content = processed_content.replace(
                            f"\\cite{{{bibitem_key}}}", 
                            f"\\cite{{{bibitem_key}}} (Q1)"
                        )
                    elif is_sa:
                        processed_content = processed_content.replace(
                            f"\\cite{{{bibitem_key}}}", 
                            f"\\cite{{{bibitem_key}}} (SA)"
                        )
                    
                    content_parts.append(processed_content)
                    self.logger.info(f"Added processed content: {len(processed_content)} chars")
                else:
                    self.logger.warning(f"No content generated from abstract {i+1}")
            
            # Add methodological synthesis if multiple papers
            if len(abstracts_data) > 2 and cluster.method:
                method_synthesis = f"These studies collectively demonstrate the effectiveness of {cluster.method} approaches "
                method_synthesis += f"in addressing {cluster.research_objective.lower()} "
                # Cite multiple papers for synthesis
                if len(bibitem_keys) >= 2:
                    method_synthesis += f"\\cite{{{','.join(bibitem_keys[:3])}}}. "
                else:
                    method_synthesis += f"\\cite{{{bibitem_keys[0]}}}. "
                content_parts.append(method_synthesis)
        else:
            self.logger.warning(f"No substantial abstracts found for cluster {cluster.cluster_id}")
        
        # If no substantial abstracts available, use claims as enhanced fallback
        if not content_parts and cluster.claims:
            fallback_content = f"Research in {cluster.theme.lower()} has investigated {cluster.research_objective}. "
            
            # Extract key findings from claims
            key_findings = []
            for claim in cluster.claims[:3]:  # Use top 3 claims
                if claim.statement and len(claim.statement) > 20:
                    # Clean up claim statement for literature
                    statement = claim.statement.strip()
                    if not statement.endswith('.'):
                        statement += '.'
                    key_findings.append(statement)
            
            if key_findings:
                fallback_content += " ".join(key_findings) + " "
            
            if bibitem_keys:
                fallback_content += f"\\cite{{{bibitem_keys[0]}}} "
            content_parts.append(fallback_content)
        
        # Add contradiction analysis if present
        if cluster.contradictions and len(bibitem_keys) > 1:
            contradiction_text = f"However, contradictory findings have been reported: {cluster.contradictions[0]} "
            contradiction_text += f"\\cite{{{','.join(bibitem_keys[:2])}}}. "
            content_parts.append(contradiction_text)
        
        # Add agreement reinforcement if present
        if cluster.agreements and len(bibitem_keys) > 1:
            agreement_text = f"Consistent findings across multiple studies support {cluster.agreements[0]} "
            agreement_text += f"\\cite{{{','.join(bibitem_keys[:2])}}}. "
            content_parts.append(agreement_text)
        
        # Combine all parts into coherent paragraph
        full_paragraph = "".join(content_parts)
        
        # Clean up any double spaces or formatting issues
        import re
        full_paragraph = re.sub(r'\s+', ' ', full_paragraph)
        full_paragraph = full_paragraph.strip()
        
        claim_ids = [getattr(claim, 'id', claim.id) for claim in cluster.claims]
        
        return full_paragraph, citations, claim_ids
    
    async def _build_cluster_paragraph_from_table(
        self,
        cluster: ClaimCluster,
        mode: str,
        rows_by_paper: Dict[str, List[EvidenceRow]],
        rows_by_key: Dict[str, EvidenceRow],
    ) -> Tuple[str, List[str], List[str], List[Any]]:
        """Build a cluster's paragraph FROM the evidence table instead of raw
        abstracts. Falls back to the legacy abstract-based paragraph (the
        original _build_cluster_paragraph) when the cluster's papers produced
        zero evidence rows, keeping runs resilient to partial extraction failure.

        Every generated sentence is verified against rows_by_key before being
        accepted: an unsupported sentence (citing a key with no matching row,
        or no \\cite{} at all) is a build error, not a silently dropped one.
        """
        cluster_rows: List[EvidenceRow] = []
        seen_ids = set()
        for paper in cluster.papers:
            pid = paper_id_for(paper)
            for row in rows_by_paper.get(pid, []):
                if row.id not in seen_ids:
                    cluster_rows.append(row)
                    seen_ids.add(row.id)

        claim_ids = [getattr(claim, 'id', claim.id) for claim in cluster.claims]

        if not cluster_rows:
            # No evidence rows for this cluster's papers — fall back to the
            # legacy abstract-based paragraph builder.
            text, citations, legacy_claim_ids = await self._build_cluster_paragraph(cluster, mode)
            return text, citations, legacy_claim_ids, []

        usable_rows = [r for r in cluster_rows if r.bibitem_key]
        scored = getattr(self, "grounding_mode", "reject") == "scored"

        if mode == "llm" and usable_rows:
            raw = self._llm_synthesize_from_rows(cluster, usable_rows)
            if scored:
                # Keep every sentence, flag the unverifiable ones. No raise, no retry.
                sentences = narrative_verifier.verify_paragraph_scored(raw, rows_by_key)
                text = raw
            else:
                try:
                    sentences = narrative_verifier.verify_paragraph(raw, rows_by_key)
                    text = raw
                except UnsupportedSentenceError:
                    raw = self._llm_synthesize_from_rows(cluster, usable_rows, correction=True)
                    # One retry only — a second failure propagates as a genuine build error.
                    sentences = narrative_verifier.verify_paragraph(raw, rows_by_key)
                    text = raw
        else:
            text = " ".join(
                f"{r.population or 'The study'} applied {r.method or 'the method'} on "
                f"{r.dataset or 'the dataset'}, reporting {r.result or 'a result'} "
                f"\\cite{{{r.bibitem_key}}}."
                for r in usable_rows
            )
            if not usable_rows:
                sentences = []
            elif scored:
                sentences = narrative_verifier.verify_paragraph_scored(text, rows_by_key)
            else:
                sentences = narrative_verifier.verify_paragraph(text, rows_by_key)

        citations = [r.bibitem_key for r in usable_rows]
        return text, citations, claim_ids, sentences

    def _llm_synthesize_from_rows(
        self,
        cluster: ClaimCluster,
        rows: List[EvidenceRow],
        correction: bool = False,
    ) -> str:
        """Ask the LLM to write one paragraph FROM the evidence table rows
        (not raw abstracts) — this is the literal 'generated from the table'
        requirement. Each row line is compact and carries its own \\cite{} key
        so the LLM cannot cite a paper it wasn't given a row for."""
        row_lines = "\n".join(
            f"[{r.bibitem_key}] population={r.population or 'n/a'}; method={r.method or 'n/a'}; "
            f"dataset={r.dataset or 'n/a'}; metric={r.metric or 'n/a'}; result={r.result or 'n/a'}; "
            f"limitation={r.limitation or 'n/a'}"
            for r in rows
        )
        correction_note = (
            "\nYour previous answer stated something not present in the rows below — "
            "restate using only facts from these rows.\n" if correction else ""
        )
        prompt = (
            "Write ONE flowing academic literature-review paragraph (120-220 words) "
            f"synthesizing the evidence-table rows below on the theme of "
            f"'{cluster.theme}' ({cluster.research_objective}). "
            "Use ONLY the fields given in each row — do not invent results, numbers, "
            "or facts not present in the rows. Write in third person academic tone. "
            "Cite each source inline with LaTeX \\cite{key} using the bracketed key "
            "shown before each row, placed right after the sentence that draws on it. "
            f"Every sentence must end with at least one \\cite{{}} key.{correction_note}"
            "Return ONLY the paragraph text, no heading, no markdown, no preamble.\n\n"
            f"Evidence rows:\n{row_lines}"
        )
        raw = llm_client.chat(
            prompt,
            max_tokens=512,
            temperature=0.2,
            tracker=self.tracker,
            purpose="literature_synthesis_from_table",
        ).strip()
        raw = re.sub(r"^```\w*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return raw

    def _build_evidence_synthesis_section(self, matrix: Optional[SynthesisMatrix]) -> LiteratureSection:
        """One bullet per non-blank matrix cell (using cell.summary, which
        already carries \\cite{} keys), plus one bullet per blank cell naming
        its matched gap's description."""
        if matrix is None or not matrix.cells:
            content = "No methods x datasets evidence was available to synthesize."
            return LiteratureSection(
                section_type='evidence_synthesis', title='Evidence Synthesis', content=content,
            )

        lines = []
        for cell in matrix.cells:
            if cell.status == "blank":
                if cell.gap_id:
                    lines.append(f"- **Gap** ({cell.method} x {cell.dataset}): no study covers this combination.")
            else:
                lines.append(f"- **{cell.method} x {cell.dataset}**: {cell.summary}")

        content = "\n".join(lines) if lines else "No synthesis-matrix findings to report."
        citations = [key for cell in matrix.cells for key in narrative_verifier.extract_cite_keys(cell.summary)]

        return LiteratureSection(
            section_type='evidence_synthesis',
            title='Evidence Synthesis',
            content=content,
            citations=list(set(citations)),
        )

    def _build_prisma_counts(
        self, research_results: ResearchResults, evidence_rows: List[EvidenceRow],
    ) -> PrismaCounts:
        total_papers = len(research_results.papers)
        excluded_no_abstract = len([p for p in research_results.papers if not p.abstract or len(p.abstract.strip()) < 20])
        excluded_extraction_failed = len([r for r in evidence_rows if r.confidence == 0.0])
        included = total_papers - excluded_extraction_failed
        duplicates_removed = research_results.run_metadata.get("papers_before_dedup", total_papers) - total_papers
        return PrismaCounts(
            identified=research_results.run_metadata.get("papers_before_dedup", total_papers),
            duplicates_removed=max(duplicates_removed, 0),
            screened=total_papers,
            excluded_no_abstract=excluded_no_abstract,
            excluded_extraction_failed=excluded_extraction_failed,
            included=max(included, 0),
        )

    def _llm_synthesize_paragraph(
        self,
        cluster: ClaimCluster,
        abstracts_data: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Ask the LLM to synthesize one literature-review paragraph, grounded
        strictly in the supplied abstracts, citing each with \\cite{bibitem_key}.
        Returns None on any failure so the caller falls back to the
        sentence-extraction heuristic."""
        sources = "\n\n".join(
            f"[{a['bibitem_key']}] {a['abstract'][:1200]}"
            for a in abstracts_data
        )
        prompt = (
            "Write ONE flowing academic literature-review paragraph (120-220 words) "
            f"synthesizing the following paper abstracts on the theme of "
            f"'{cluster.theme}' ({cluster.research_objective}). "
            "Use only facts stated in the abstracts below — do not invent results, "
            "numbers, or claims not present in the text. Write in third person "
            "academic tone. Cite each source inline with LaTeX \\cite{key} using "
            "the bracketed key shown before each abstract, placed right after the "
            "sentence that draws on it. Return ONLY the paragraph text, no heading, "
            "no markdown, no preamble.\n\n"
            f"Sources:\n{sources}"
        )
        try:
            raw = llm_client.chat(
                prompt,
                max_tokens=512,
                temperature=0.2,
                tracker=self.tracker,
                purpose="literature_synthesis",
            ).strip()
            raw = re.sub(r"^```\w*\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            if not raw or "\\cite{" not in raw:
                self.logger.warning("LLM literature synthesis missing citations; falling back")
                return None
            return raw + " "
        except Exception as e:
            self.logger.warning(f"LLM literature synthesis failed: {e}; falling back to rules")
            return None

    def _process_abstract_for_literature(self, abstract, bibitem_key):
        """Process abstract to create literature content with LaTeX citations."""
        
        # Clean abstract
        abstract = abstract.strip()
        if not abstract:
            self.logger.warning("Empty abstract provided")
            return ""
        
        self.logger.info(f"Processing abstract of {len(abstract)} characters for {bibitem_key}")
        
        # Remove common abstract prefixes and suffixes
        prefixes_to_remove = [
            "Abstract:", "ABSTRACT:", "Summary:", "SUMMARY:",
            "Background:", "BACKGROUND:", "Objective:", "OBJECTIVE:",
            "Purpose:", "PURPOSE:", "Introduction:", "INTRODUCTION:",
            "Methods:", "METHODS:", "Results:", "RESULTS:",
            "Conclusion:", "CONCLUSION:", "Conclusions:", "CONCLUSIONS:"
        ]
        
        original_abstract = abstract
        for prefix in prefixes_to_remove:
            if abstract.startswith(prefix):
                abstract = abstract[len(prefix):].strip()
                self.logger.info(f"Removed prefix '{prefix}'")
        
        # Remove common suffixes and metadata
        suffixes_to_remove = [
            "© 2023", "© 2024", "© 2025", "All rights reserved",
            "Keywords:", "KEYWORDS:", "Key words:", "KEY WORDS:",
            "Funding:", "FUNDING:", "Acknowledgments:", "ACKNOWLEDGMENTS:",
            "Conflict of interest:", "CONFLICT OF INTEREST:",
            "Author contributions:", "AUTHOR CONTRIBUTIONS:"
        ]
        
        for suffix in suffixes_to_remove:
            if suffix in abstract:
                abstract = abstract.split(suffix)[0].strip()
                self.logger.info(f"Removed suffix '{suffix}'")
        
        # Split into sentences and clean them
        import re
        sentences = re.split(r'[.!?]+', abstract)
        clean_sentences = []
        
        self.logger.info(f"Found {len(sentences)} sentences in abstract")
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 15:  # Only meaningful sentences
                # Remove common research paper phrases that don't add value to literature
                skip_phrases = [
                    "in this paper", "in this study", "in this work", "we present",
                    "we propose", "we show", "we demonstrate", "our results",
                    "our findings", "our approach", "our method", "this paper",
                    "this study", "this work", "the present study"
                ]
                
                sentence_lower = sentence.lower()
                should_skip = any(phrase in sentence_lower for phrase in skip_phrases)
                
                if not should_skip:
                    clean_sentences.append(sentence)
                else:
                    self.logger.info(f"Skipped sentence with research phrase: {sentence[:50]}...")
        
        self.logger.info(f"Kept {len(clean_sentences)} clean sentences")
        
        if not clean_sentences:
            self.logger.warning("No clean sentences found after filtering")
            return ""
        
        # Select the most informative sentences (usually 2-3 from the middle/end)
        # Skip the first sentence as it's often too general
        if len(clean_sentences) > 3:
            selected_sentences = clean_sentences[1:4]  # Take sentences 2-4
        elif len(clean_sentences) > 1:
            selected_sentences = clean_sentences[1:]   # Skip first sentence
        else:
            selected_sentences = clean_sentences       # Use all if only one
        
        self.logger.info(f"Selected {len(selected_sentences)} sentences for literature")
        
        # Process sentences to create academic literature content
        processed_sentences = []
        
        for i, sentence in enumerate(selected_sentences):
            if not sentence:
                continue
            
            # Clean up sentence
            sentence = sentence.strip()
            
            # Convert first-person to third-person for academic tone
            sentence = re.sub(r'\bwe\b', 'the authors', sentence, flags=re.IGNORECASE)
            sentence = re.sub(r'\bour\b', 'their', sentence, flags=re.IGNORECASE)
            
            # Ensure sentence ends with period
            if not sentence.endswith('.'):
                sentence += '.'
            
            # Add LaTeX citation strategically
            if i == 0:  # First sentence - introduce the work
                sentence = sentence.rstrip('.') + f" \\cite{{{bibitem_key}}}."
            elif i == len(selected_sentences) - 1 and len(selected_sentences) > 1:  # Last sentence if multiple
                sentence = sentence.rstrip('.') + f" \\cite{{{bibitem_key}}}."
            
            processed_sentences.append(sentence)
        
        # Join sentences with proper spacing
        literature_text = " ".join(processed_sentences)
        
        # Ensure proper paragraph ending
        if not literature_text.endswith('.'):
            literature_text += '.'
        
        literature_text += " "
        
        self.logger.info(f"Generated literature text of {len(literature_text)} characters")
        
        return literature_text
    
    async def _build_comparative_section(
        self, 
        clusters: List[ClaimCluster], 
        section_info: Dict[str, Any]
    ) -> LiteratureSection:
        """Build the comparative analysis section."""
        
        relevant_clusters = [c for c in clusters if c.contradictions or c.agreements]
        
        content_parts = []
        all_citations = []
        all_claim_ids = []
        
        # Analyze contradictions
        if any(c.contradictions for c in relevant_clusters):
            contradiction_content = "### Contradictory Findings\n\n"
            for cluster in relevant_clusters:
                if cluster.contradictions:
                    contradiction_content += f"In {cluster.theme.lower()} research, {cluster.contradictions[0]} "
                    contradiction_content += f"This highlights the need for further investigation in this area.\n\n"
            content_parts.append(contradiction_content)
        
        # Analyze agreements
        if any(c.agreements for c in relevant_clusters):
            agreement_content = "### Consistent Findings\n\n"
            for cluster in relevant_clusters:
                if cluster.agreements:
                    agreement_content += f"There is consensus in {cluster.theme.lower()} research regarding "
                    agreement_content += f"{cluster.agreements[0]}\n\n"
            content_parts.append(agreement_content)
        
        # Q-ranking analysis
        q_analysis = self._analyze_q_rankings(relevant_clusters)
        if q_analysis:
            content_parts.append(f"### Quality Analysis\n\n{q_analysis}")
        
        content = "\n".join(content_parts) if content_parts else "No significant contradictions or agreements found in the analyzed literature."
        
        return LiteratureSection(
            section_type='comparative_analysis',
            title='Comparative Analysis',
            content=content,
            citations=all_citations,
            claim_ids=all_claim_ids
        )
    
    def _analyze_q_rankings(self, clusters: List[ClaimCluster]) -> str:
        """Analyze the distribution of Q-rankings across clusters."""
        
        total_q1 = sum(len([p for p in c.q_ranking.values() if p == 'Q1']) for c in clusters)
        total_q2 = sum(len([p for p in c.q_ranking.values() if p == 'Q2']) for c in clusters)
        total_q3 = sum(len([p for p in c.q_ranking.values() if p == 'Q3']) for c in clusters)
        total_sa = sum(len(c.sa_papers) for c in clusters)
        
        total_papers = total_q1 + total_q2 + total_q3
        
        if total_papers == 0:
            return ""
        
        analysis = f"""
The literature analysis reveals a distribution of {total_q1} Q1 papers ({total_q1/total_papers*100:.1f}%), 
{total_q2} Q2 papers ({total_q2/total_papers*100:.1f}%), and {total_q3} Q3 papers ({total_q3/total_papers*100:.1f}%). 
Additionally, {total_sa} papers were identified as systematic analyses or reviews, providing comprehensive 
overviews of their respective domains.
        """.strip()
        
        return analysis
    
    async def _build_trends_section(
        self, 
        clusters: List[ClaimCluster], 
        section_info: Dict[str, Any]
    ) -> LiteratureSection:
        """Build the trends and evolution section."""
        
        # Analyze temporal trends
        year_themes = defaultdict(list)
        for cluster in clusters:
            for paper in cluster.papers:
                if paper.year:
                    year_themes[paper.year].append(cluster.theme)
        
        # Analyze methodological evolution
        method_evolution = defaultdict(list)
        for cluster in clusters:
            if cluster.method:
                papers_with_years = [p for p in cluster.papers if p.year]
                if papers_with_years:  # Only process if there are papers with years
                    avg_year = sum(p.year for p in papers_with_years) / len(papers_with_years)
                    method_evolution[cluster.method].append(avg_year)
        
        content_parts = []
        
        # Temporal trends
        if year_themes:
            sorted_years = sorted(year_themes.keys())
            early_themes = set(year_themes[sorted_years[0]]) if sorted_years else set()
            recent_themes = set(year_themes[sorted_years[-1]]) if sorted_years else set()
            
            temporal_content = f"""
### Temporal Evolution

The research landscape has evolved significantly over the analyzed period. Early work (around {sorted_years[0] if sorted_years else 'N/A'}) 
focused primarily on {', '.join(list(early_themes)[:3]) if early_themes else 'foundational approaches'}. 
Recent developments (around {sorted_years[-1] if sorted_years else 'N/A'}) have shifted towards 
{', '.join(list(recent_themes)[:3]) if recent_themes else 'advanced methodologies'}.
            """.strip()
            content_parts.append(temporal_content)
        
        # Methodological trends
        if method_evolution:
            method_content = "### Methodological Trends\n\n"
            for method, years in method_evolution.items():
                avg_year = sum(years) / len(years)
                method_content += f"{method.title()} approaches have been predominantly explored around {avg_year:.0f}. "
            content_parts.append(method_content)
        
        content = "\n\n".join(content_parts) if content_parts else "Temporal and methodological trends analysis requires more diverse temporal data."
        
        return LiteratureSection(
            section_type='trends',
            title='Trends and Evolution',
            content=content,
            citations=[],
            claim_ids=[]
        )
    
    def _generate_bibitem_key(self, paper: PaperMetadata) -> str:
        """Delegates to CustomCitationFormatter — kept as a thin wrapper so
        existing direct callers (tests) keep working after the bibliography
        logic was consolidated onto that formatter instead of being duplicated
        here."""
        return self.citation_formatter._generate_bibitem_key(paper)

    def _extract_volume_info(self, paper: PaperMetadata) -> Dict[str, Optional[str]]:
        """Extract volume, issue, and page information from paper metadata or DOI.

        NOTE: kept as its own dict-returning implementation rather than delegating
        to CustomCitationFormatter — that formatter's same-named private method
        returns a formatted LaTeX string fragment (or None), not this dict shape,
        despite constructing an identical-looking dict internally. Blind delegation
        here would silently break every caller expecting .get('volume'/'issue'/'pages').
        """
        volume_info: Dict[str, Optional[str]] = {
            'volume': None,
            'issue': None,
            'pages': None,
            'article_number': None,
        }

        if paper.doi and requests:
            try:
                import time

                doi = paper.doi.strip()
                if doi.startswith('https://doi.org/'):
                    doi = doi.replace('https://doi.org/', '')
                elif doi.startswith('http://dx.doi.org/'):
                    doi = doi.replace('http://dx.doi.org/', '')
                elif doi.startswith('doi:'):
                    doi = doi.replace('doi:', '')

                crossref_url = f"https://api.crossref.org/works/{doi}"
                headers = {
                    'User-Agent': 'Research System/1.0 (mailto:research@example.com)',
                    'Accept': 'application/json',
                }

                response = requests.get(crossref_url, headers=headers, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    work = data.get('message', {})

                    if 'volume' in work and work['volume']:
                        volume_info['volume'] = str(work['volume']).strip()
                    if 'issue' in work and work['issue']:
                        volume_info['issue'] = str(work['issue']).strip()
                    if 'page' in work and work['page']:
                        pages = str(work['page']).strip()
                        if pages:
                            volume_info['pages'] = pages
                    elif 'article-number' in work and work['article-number']:
                        article_num = str(work['article-number']).strip()
                        volume_info['article_number'] = article_num
                        volume_info['pages'] = article_num

                    time.sleep(0.1)
                elif response.status_code == 404:
                    self.logger.info(f"DOI {doi} not found in CrossRef (404)")
                else:
                    self.logger.warning(f"CrossRef API returned status {response.status_code} for DOI {doi}")

            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout while fetching bibliographic data for DOI {paper.doi}")
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Request error while fetching bibliographic data for DOI {paper.doi}: {e}")
            except Exception as e:
                self.logger.warning(f"Unexpected error while fetching bibliographic data for DOI {paper.doi}: {e}")
        elif paper.doi and not requests:
            self.logger.warning("Requests library not available, skipping CrossRef API call")

        if not any([volume_info['volume'], volume_info['issue'], volume_info['pages']]):
            if paper.venue:
                venue_lower = paper.venue.lower()
                vol_match = re.search(r'vol(?:ume)?\.?\s*(\d+)', venue_lower)
                if vol_match:
                    volume_info['volume'] = vol_match.group(1)
                issue_match = re.search(r'(?:no|issue)\.?\s*(\d+)', venue_lower)
                if issue_match:
                    volume_info['issue'] = issue_match.group(1)
                vol_issue_match = re.search(r'(\d+)\((\d+)\)', venue_lower)
                if vol_issue_match:
                    volume_info['volume'] = vol_issue_match.group(1)
                    volume_info['issue'] = vol_issue_match.group(2)

        return volume_info

    def get_literature_stats(self, document: LiteratureDocument) -> Dict[str, Any]:
        """Get statistics about the generated literature."""
        
        total_words = sum(len(section.content.split()) for section in document.sections)
        total_citations = len(set(citation for section in document.sections for citation in section.citations))
        
        return {
            'total_sections': len(document.sections),
            'total_words': total_words,
            'total_citations': total_citations,
            'total_papers': document.metadata['total_papers'],
            'q1_papers': document.metadata['q1_papers'],
            'q2_papers': document.metadata['q2_papers'],
            'q3_papers': document.metadata['q3_papers'],
            'sa_papers': document.metadata['sa_papers'],
            'date_range': document.outline.date_range,
            'generated_at': document.generated_at.isoformat()
        }
