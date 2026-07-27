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
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import re
from datetime import datetime

from . import llm_client

# Import requests with fallback
try:
    import requests
except ImportError:
    requests = None

# Try relative imports first, then absolute
try:
    from ..models.data_models import (
        Claim, PaperMetadata, ResearchResults, TopicMap, ClaimCluster,
        LiteratureSection, LiteratureOutline, LiteratureDocument, LiteratureFilter
    )
except ImportError:
    # Fallback to absolute imports for testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from models.data_models import (
        Claim, PaperMetadata, ResearchResults, TopicMap, ClaimCluster,
        LiteratureSection, LiteratureOutline, LiteratureDocument, LiteratureFilter
    )

logger = logging.getLogger(__name__)

class LiteratureBuilderAgent:
    """Agent responsible for building structured academic literature from claims."""
    
    def __init__(self, mode: Optional[str] = None):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.mode = mode  # None = auto: "llm" if a provider is available
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

    def _resolve_mode(self) -> str:
        mode = self.mode or os.getenv("LITERATURE_MODE")
        if mode in ("llm", "rules"):
            return mode
        return "llm" if llm_client.get_provider() is not None else "rules"

    async def process(self, research_results: ResearchResults) -> LiteratureDocument:
        """
        Main processing function to build literature from research results.
        
        Args:
            research_results: Complete research results with claims and papers
            
        Returns:
            LiteratureDocument: Structured academic literature
        """
        mode = self._resolve_mode()
        self.logger.info(f"Starting literature building process (mode={mode})")

        try:
            # Step 1: Classify papers by Q-ranking and SA status
            classified_papers = self._classify_papers(research_results.papers)

            # Step 2: Cluster claims by themes and methods
            claim_clusters = await self._cluster_claims(
                research_results.claims,
                research_results.papers,
                research_results.contradictions,
                classified_papers
            )

            # Step 3: Generate literature outline
            outline = self._generate_outline(
                claim_clusters,
                research_results.topic_map,
                research_results.papers
            )

            # Step 4: Build literature sections
            sections = await self._build_sections(claim_clusters, outline, mode)
            
            # Step 5: Generate bibliography
            bibliography = self._generate_bibliography(research_results.papers)
            
            # Step 6: Create final document
            document = LiteratureDocument(
                outline=outline,
                sections=sections,
                bibliography=bibliography,
                metadata={
                    'total_papers': len(research_results.papers),
                    'total_claims': len(research_results.claims),
                    'q1_papers': len([p for p in classified_papers if classified_papers[p]['q_rank'] == 'Q1']),
                    'q2_papers': len([p for p in classified_papers if classified_papers[p]['q_rank'] == 'Q2']),
                    'q3_papers': len([p for p in classified_papers if classified_papers[p]['q_rank'] == 'Q3']),
                    'sa_papers': len([p for p in classified_papers if classified_papers[p]['is_sa']]),
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
        
        # Create paper lookup
        paper_lookup = {getattr(p, 'id', f"paper_{hash(p.title)}"): p for p in papers}
        
        # Group claims by similarity
        clusters = []
        processed_claims = set()
        
        for i, claim in enumerate(claims):
            claim_id = getattr(claim, 'id', claim.id)
            if claim_id in processed_claims:
                continue
            
            # Find similar claims
            similar_claims = [claim]
            similar_papers = [paper_lookup.get(getattr(claim, 'paper_id', claim.paper_id))]
            
            for j, other_claim in enumerate(claims[i+1:], i+1):
                other_claim_id = getattr(other_claim, 'id', other_claim.id)
                if other_claim_id in processed_claims:
                    continue
                
                # Check similarity based on keywords, methods, datasets
                if self._are_claims_similar(claim, other_claim):
                    similar_claims.append(other_claim)
                    similar_papers.append(paper_lookup.get(getattr(other_claim, 'paper_id', other_claim.paper_id)))
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
        mode: str = "rules"
    ) -> List[LiteratureSection]:
        """Build the actual literature sections."""

        sections = []
        cluster_lookup = {c.cluster_id: c for c in clusters}

        for section_info in outline.sections:
            section_type = section_info['type']

            if section_type == 'introduction':
                section = await self._build_introduction_section(clusters, outline)
            elif section_type == 'related_work':
                section = await self._build_related_work_section(clusters, section_info, mode)
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
        mode: str = "rules"
    ) -> LiteratureSection:
        """Build the related work section."""

        subsections = []

        # Group clusters by method or theme
        method_groups = defaultdict(list)
        for cluster in clusters:
            key = cluster.method or cluster.theme
            method_groups[key].append(cluster)

        content_parts = []
        all_citations = []
        all_claim_ids = []

        for method, method_clusters in method_groups.items():
            subsection_content = await self._build_method_subsection(method, method_clusters, mode)
            content_parts.append(subsection_content['content'])
            all_citations.extend(subsection_content['citations'])
            all_claim_ids.extend(subsection_content['claim_ids'])
        
        content = "\n\n".join(content_parts)
        
        return LiteratureSection(
            section_type='related_work',
            title='Related Work',
            content=content,
            citations=list(set(all_citations)),
            claim_ids=all_claim_ids
        )
    
    async def _build_method_subsection(
        self,
        method: str,
        clusters: List[ClaimCluster],
        mode: str = "rules"
    ) -> Dict[str, Any]:
        """Build a subsection for a specific method or theme."""

        paragraphs = []
        citations = []
        claim_ids = []

        for cluster in clusters:
            paragraph, para_citations, para_claim_ids = await self._build_cluster_paragraph(cluster, mode)
            paragraphs.append(paragraph)
            citations.extend(para_citations)
            claim_ids.extend(para_claim_ids)
        
        content = f"### {method.title()}\n\n" + "\n\n".join(paragraphs)
        
        return {
            'content': content,
            'citations': citations,
            'claim_ids': claim_ids
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

    def _generate_bibitem_key(self, paper):
        """Generate bibitem key from authors and year (e.g., KaPa23)."""
        if not paper.authors:
            return f"Un{paper.year % 100:02d}"
        
        # Get first 2-3 authors for key generation
        authors_for_key = paper.authors[:3] if len(paper.authors) >= 3 else paper.authors[:2]
        
        # Extract first two letters of last names
        key_parts = []
        for author in authors_for_key:
            # Handle different author name formats
            name_parts = author.strip().split()
            if name_parts:
                last_name = name_parts[-1]  # Last part is surname
                if len(last_name) >= 2:
                    key_parts.append(last_name[:2].title())
                elif len(last_name) == 1:
                    key_parts.append(last_name.upper())
        
        # Add year (last 2 digits)
        year_suffix = paper.year % 100 if paper.year else 0
        
        key = "".join(key_parts) + f"{year_suffix:02d}"
        return key
    
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
    
    def _generate_bibliography(self, papers: List[PaperMetadata]) -> List[str]:
        """Generate bibliography entries with correct custom format and accurate data."""
        
        bibliography = []
        
        for paper in sorted(papers, key=lambda p: (p.authors[0] if p.authors else 'Unknown', p.year)):
            # Generate bibitem key
            bibitem_key = self._generate_bibitem_key(paper)
            
            # Format authors with initials first
            formatted_authors = self._format_authors_custom(paper.authors)
            
            # Format title (first letter capital, proper nouns capitalized)
            formatted_title = self._format_title_custom(paper.title)
            
            # Get venue information
            venue = paper.venue or 'Unknown Venue'
            year = paper.year or 'Unknown Year'
            
            # Extract volume, issue, pages from DOI or other sources if available
            volume_info = self._extract_volume_info(paper)
            
            # Build custom citation format: \bibitem{KaPa23} F.M. Last, Title, Journal \textbf{vol}(issue) (year) pages. DOI
            entry = f"\\bibitem{{{bibitem_key}}} {formatted_authors}, {formatted_title}, {venue}"
            
            # Add volume and issue information ONLY if we have real data
            if volume_info['volume']:
                entry += f" \\textbf{{{volume_info['volume']}}}"
                if volume_info['issue']:
                    entry += f"({volume_info['issue']})"
            
            # Add year
            entry += f" ({year})"
            
            # Add pages ONLY if we have real data
            if volume_info['pages']:
                entry += f" {volume_info['pages']}"
            
            # Add DOI
            if paper.doi:
                if paper.doi.startswith('http'):
                    entry += f". {paper.doi}"
                else:
                    entry += f". https://doi.org/{paper.doi}"
            elif paper.url:
                entry += f". {paper.url}"
            
            bibliography.append(entry)
        
        return bibliography
    
    def _format_authors_custom(self, authors):
        """Format authors with initials first, then last name (F.M. Last format)."""
        if not authors:
            return "Unknown Author"
        
        formatted_authors = []
        
        for author in authors:
            author = author.strip()
            parts = author.split()
            
            if len(parts) < 2:
                formatted_authors.append(author)
                continue
            
            # Check if author is already in correct format (e.g., "Y. Saad", "M.H. Schultz")
            if len(parts) == 2 and len(parts[0]) <= 4 and '.' in parts[0]:
                # Already in format like "Y. Saad" or "M.H. Schultz"
                formatted_authors.append(author)
                continue
                
            # Last part is last name
            last_name = parts[-1]
            
            # Everything else is first/middle names
            first_middle = parts[:-1]
            
            # Create initials
            initials = []
            for name in first_middle:
                if name and name[0].isalpha():
                    # Handle names that might already have periods
                    if name.endswith('.'):
                        initials.append(name)
                    else:
                        initials.append(f"{name[0].upper()}.")
            
            # Format as "F.M. Last" (initials first, then last name)
            if initials:
                formatted_authors.append(f"{''.join(initials)} {last_name}")
            else:
                formatted_authors.append(last_name)
        
        return ", ".join(formatted_authors)
    
    def _format_title_custom(self, title):
        """Format title with only first letter capital, except proper nouns."""
        if not title:
            return "Unknown Title"
        
        # Clean title
        title = title.strip()
        if title.endswith('.'):
            title = title[:-1]
        
        # Convert to lowercase first
        title_lower = title.lower()
        
        # Capitalize first letter
        if title_lower:
            title_formatted = title_lower[0].upper() + title_lower[1:]
        else:
            title_formatted = title_lower
        
        # Capitalize proper nouns
        proper_nouns = ["wiener", "euler", "hamilton", "fibonacci", "pascal", "newton", "gauss",
                       "fourier", "laplace", "bayes", "markov", "poisson", "bernoulli",
                       "covid", "sars", "hiv", "aids", "dna", "rna", "pcr", "crispr"]
        
        for proper_noun in proper_nouns:
            import re
            pattern = r'\b' + re.escape(proper_noun.lower()) + r'\b'
            replacement = proper_noun.capitalize()
            title_formatted = re.sub(pattern, replacement, title_formatted, flags=re.IGNORECASE)
        
        return title_formatted
    
    def _extract_volume_info(self, paper):
        """Extract volume, issue, and page information from paper metadata or DOI."""
        volume_info = {
            'volume': None,
            'issue': None,
            'pages': None,
            'article_number': None
        }
        
    def _extract_volume_info(self, paper):
        """Extract volume, issue, and page information from paper metadata or DOI."""
        volume_info = {
            'volume': None,
            'issue': None,
            'pages': None,
            'article_number': None
        }
        
        # Try to extract from DOI using CrossRef API
        if paper.doi and requests:
            try:
                import time
                
                # Clean DOI - handle various DOI formats
                doi = paper.doi.strip()
                if doi.startswith('https://doi.org/'):
                    doi = doi.replace('https://doi.org/', '')
                elif doi.startswith('http://dx.doi.org/'):
                    doi = doi.replace('http://dx.doi.org/', '')
                elif doi.startswith('doi:'):
                    doi = doi.replace('doi:', '')
                
                # Query CrossRef API for accurate bibliographic data
                crossref_url = f"https://api.crossref.org/works/{doi}"
                headers = {
                    'User-Agent': 'Research System/1.0 (mailto:research@example.com)',
                    'Accept': 'application/json'
                }
                
                self.logger.info(f"Fetching bibliographic data for DOI: {doi}")
                response = requests.get(crossref_url, headers=headers, timeout=10)  # Reduced timeout
                
                if response.status_code == 200:
                    data = response.json()
                    work = data.get('message', {})
                    
                    # Extract volume
                    if 'volume' in work and work['volume']:
                        volume_info['volume'] = str(work['volume']).strip()
                    
                    # Extract issue
                    if 'issue' in work and work['issue']:
                        volume_info['issue'] = str(work['issue']).strip()
                    
                    # Extract pages - handle different formats
                    if 'page' in work and work['page']:
                        pages = str(work['page']).strip()
                        # Handle different page formats: "123-145", "123--145", "e123456", etc.
                        if pages:
                            volume_info['pages'] = pages
                    elif 'article-number' in work and work['article-number']:
                        article_num = str(work['article-number']).strip()
                        volume_info['article_number'] = article_num
                        volume_info['pages'] = article_num  # Use article number as pages
                    
                    # Log successful extraction
                    self.logger.info(f"Successfully extracted: vol={volume_info['volume']}, issue={volume_info['issue']}, pages={volume_info['pages']}")
                    
                    # Small delay to be respectful to CrossRef API
                    time.sleep(0.1)
                    
                elif response.status_code == 404:
                    self.logger.info(f"DOI {doi} not found in CrossRef (404) - this is normal for test/fake DOIs")
                else:
                    self.logger.warning(f"CrossRef API returned status {response.status_code} for DOI {doi}")
                    
            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout while fetching bibliographic data for DOI {paper.doi} - continuing without volume info")
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Request error while fetching bibliographic data for DOI {paper.doi}: {str(e)}")
            except Exception as e:
                self.logger.warning(f"Unexpected error while fetching bibliographic data for DOI {paper.doi}: {str(e)}")
        elif paper.doi and not requests:
            self.logger.warning("Requests library not available, skipping CrossRef API call")
        
        # Only use fallback values if we couldn't get any real data
        # This ensures we don't override real data with fake data
        if not any([volume_info['volume'], volume_info['issue'], volume_info['pages']]):
            # Try to extract from venue name if it contains volume/issue info
            if paper.venue:
                venue_lower = paper.venue.lower()
                import re
                
                # Look for patterns like "vol. 25, no. 3" or "25(3)" in venue
                vol_match = re.search(r'vol(?:ume)?\.?\s*(\d+)', venue_lower)
                if vol_match:
                    volume_info['volume'] = vol_match.group(1)
                
                issue_match = re.search(r'(?:no|issue)\.?\s*(\d+)', venue_lower)
                if issue_match:
                    volume_info['issue'] = issue_match.group(1)
                
                # Look for pattern like "25(3)" 
                vol_issue_match = re.search(r'(\d+)\((\d+)\)', venue_lower)
                if vol_issue_match:
                    volume_info['volume'] = vol_issue_match.group(1)
                    volume_info['issue'] = vol_issue_match.group(2)
        
        return volume_info
        
        # Only use fallback values if we couldn't get any real data
        # This ensures we don't override real data with fake data
        if not any([volume_info['volume'], volume_info['issue'], volume_info['pages']]):
            # Try to extract from venue name if it contains volume/issue info
            if paper.venue:
                venue_lower = paper.venue.lower()
                import re
                
                # Look for patterns like "vol. 25, no. 3" or "25(3)" in venue
                vol_match = re.search(r'vol(?:ume)?\.?\s*(\d+)', venue_lower)
                if vol_match:
                    volume_info['volume'] = vol_match.group(1)
                
                issue_match = re.search(r'(?:no|issue)\.?\s*(\d+)', venue_lower)
                if issue_match:
                    volume_info['issue'] = issue_match.group(1)
                
                # Look for pattern like "25(3)" 
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