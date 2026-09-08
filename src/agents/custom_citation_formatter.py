"""
Custom Citation Formatter - Creates citations in specific academic format.
"""
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

# Import requests with fallback
try:
    import requests
except ImportError:
    requests = None

# Try relative imports first, then absolute
try:
    from ..models.data_models import PaperMetadata, Citation
    from .base_agent import BaseAgent
    from .paper_ids import paper_id_for
except ImportError:
    # Fallback to absolute imports for testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from models.data_models import PaperMetadata, Citation
    from agents.base_agent import BaseAgent
    from agents.paper_ids import paper_id_for


class CustomCitationFormatter(BaseAgent):
    """Custom citation formatter with specific academic format."""
    
    def __init__(self, memory_store=None):
        super().__init__("CustomCitationFormatter", memory_store)
        self.proper_nouns = self._load_proper_nouns()
    
    def _load_proper_nouns(self) -> List[str]:
        """Load list of proper nouns that should be capitalized."""
        return [
            "wiener", "euler", "hamilton", "fibonacci", "pascal", "newton", "gauss",
            "fourier", "laplace", "bayes", "markov", "poisson", "bernoulli",
            "covid", "sars", "hiv", "aids", "dna", "rna", "pcr", "crispr",
            "python", "java", "matlab", "tensorflow", "pytorch", "keras",
            "ieee", "acm", "aaai", "icml", "neurips", "iclr", "cvpr", "iccv",
            "nature", "science", "cell", "lancet", "nejm", "pnas", "jacs",
            "american", "european", "british", "chinese", "japanese", "german",
            "google", "microsoft", "ibm", "facebook", "amazon", "apple",
            "stanford", "mit", "harvard", "cambridge", "oxford", "berkeley"
        ]
    
    async def process(self, papers: List[PaperMetadata]) -> List[Dict[str, Any]]:
        """
        Generate custom formatted citations for papers.
        
        Args:
            papers: List of papers to format
            
        Returns:
            List of formatted citations with metadata
        """
        self.log_operation("custom_citation_start", {"paper_count": len(papers)})
        
        formatted_citations = []
        
        for paper in papers:
            try:
                citation = await self._format_paper_citation(paper)
                formatted_citations.append(citation)
            except Exception as e:
                self.logger.warning(f"Failed to format citation for {paper.title}: {e}")
        
        # Store results
        await self.store_result("custom_citations", formatted_citations)
        
        self.log_operation("custom_citation_complete", {
            "citations_generated": len(formatted_citations)
        })
        
        return formatted_citations
    
    async def _format_paper_citation(self, paper: PaperMetadata) -> Dict[str, Any]:
        """Format a single paper citation in custom format."""
        
        # Generate bibitem key
        bibitem_key = self._generate_bibitem_key(paper)
        
        # Format authors
        formatted_authors = self._format_authors_custom(paper.authors)
        
        # Format title
        formatted_title = self._format_title_custom(paper.title)
        
        # Format journal/venue
        formatted_venue = self._format_venue_custom(paper.venue)
        
        # Format volume and article number
        volume_info = self._extract_volume_info(paper)
        
        # Format year
        year = paper.year
        
        # Format page numbers
        page_numbers = self._extract_page_numbers(paper)
        
        # Format DOI
        doi_link = self._format_doi(paper.doi, paper.url)
        
        # Create the full citation
        citation_parts = []
        citation_parts.append(formatted_authors)
        citation_parts.append(formatted_title)
        citation_parts.append(formatted_venue)
        
        if volume_info:
            citation_parts.append(volume_info)
        
        citation_parts.append(f"({year})")
        
        if page_numbers:
            citation_parts.append(page_numbers)
        
        if doi_link:
            citation_parts.append(doi_link)
        
        # Join parts appropriately
        full_citation = self._join_citation_parts(citation_parts)
        
        # Create bibitem format
        bibitem_citation = f"\\bibitem{{{bibitem_key}}} {full_citation}"
        
        return {
            "paper_id": self._generate_paper_id(paper),
            "bibitem_key": bibitem_key,
            "bibitem_citation": bibitem_citation,
            "formatted_authors": formatted_authors,
            "formatted_title": formatted_title,
            "formatted_venue": formatted_venue,
            "year": year,
            "volume_info": volume_info,
            "page_numbers": page_numbers,
            "doi_link": doi_link,
            "paper_url": self._get_paper_url(paper),
            "journal_name": paper.venue,
            "original_paper": paper
        }
    
    def _generate_bibitem_key(self, paper: PaperMetadata) -> str:
        """Generate bibitem key from first 2-3 authors and year."""
        if not paper.authors:
            return f"Unknown{paper.year % 100:02d}"
        
        # Get first 2-3 authors
        authors_for_key = paper.authors[:3] if len(paper.authors) >= 3 else paper.authors[:2]
        
        # Extract first two letters of last names
        key_parts = []
        for author in authors_for_key:
            last_name = self._extract_last_name(author)
            if len(last_name) >= 2:
                key_parts.append(last_name[:2].title())
            elif len(last_name) == 1:
                key_parts.append(last_name.upper())
        
        # Add year (last 2 digits)
        year_suffix = paper.year % 100
        
        key = "".join(key_parts) + f"{year_suffix:02d}"
        return key
    
    def _format_authors_custom(self, authors: List[str]) -> str:
        """Format authors with initials first, then last name."""
        if not authors:
            return "Unknown Author"
        
        formatted_authors = []
        
        for author in authors:
            formatted_author = self._format_single_author(author)
            formatted_authors.append(formatted_author)
        
        # Join authors with commas
        if len(formatted_authors) == 1:
            return formatted_authors[0]
        elif len(formatted_authors) == 2:
            return f"{formatted_authors[0]}, {formatted_authors[1]}"
        else:
            # For 3+ authors, list all
            return ", ".join(formatted_authors)
    
    def _format_single_author(self, author: str) -> str:
        """Format single author: F.M. Last (initials first)."""
        # Clean the author name
        author = author.strip()
        
        # Split into parts
        parts = author.split()
        if len(parts) < 2:
            return author  # Return as-is if can't parse
        
        # Check if author is already in correct format (e.g., "Y. Saad", "M.H. Schultz")
        if len(parts) == 2 and len(parts[0]) <= 4 and '.' in parts[0]:
            # Already in format like "Y. Saad" or "M.H. Schultz"
            return author
        
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
            return f"{''.join(initials)} {last_name}"
        else:
            return last_name
    
    def _extract_last_name(self, author: str) -> str:
        """Extract last name from author string."""
        parts = author.strip().split()
        return parts[-1] if parts else author
    
    def _format_title_custom(self, title: str) -> str:
        """Format title with only first letter capital, except proper nouns."""
        if not title:
            return ""
        
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
        for proper_noun in self.proper_nouns:
            # Use word boundaries to match whole words
            pattern = r'\b' + re.escape(proper_noun.lower()) + r'\b'
            replacement = proper_noun.capitalize()
            title_formatted = re.sub(pattern, replacement, title_formatted, flags=re.IGNORECASE)
        
        # Capitalize after colons and question marks
        title_formatted = re.sub(r'([:\?])\s*([a-z])', 
                                lambda m: m.group(1) + ' ' + m.group(2).upper(), 
                                title_formatted)
        
        return title_formatted
    
    def _format_venue_custom(self, venue: str) -> str:
        """Format venue name."""
        if not venue:
            return ""
        
        # Clean venue name
        venue = venue.strip()
        
        # Handle common abbreviations
        venue_mappings = {
            "arXiv": "arXiv preprint",
            "arxiv": "arXiv preprint",
            "ICLR": "International Conference on Learning Representations",
            "NeurIPS": "Advances in Neural Information Processing Systems",
            "ICML": "International Conference on Machine Learning",
            "AAAI": "AAAI Conference on Artificial Intelligence"
        }
        
        return venue_mappings.get(venue, venue)
    
    def _extract_volume_info(self, paper: PaperMetadata) -> Optional[str]:
        """Extract volume and issue information using CrossRef API for accurate data."""
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
                response = requests.get(crossref_url, headers=headers, timeout=10)
                
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
                        if pages:
                            volume_info['pages'] = pages
                    elif 'article-number' in work and work['article-number']:
                        article_num = str(work['article-number']).strip()
                        volume_info['article_number'] = article_num
                        volume_info['pages'] = article_num
                    
                    self.logger.info(f"Successfully extracted: vol={volume_info['volume']}, issue={volume_info['issue']}, pages={volume_info['pages']}")
                    
                    # Small delay to be respectful to CrossRef API
                    time.sleep(0.1)
                    
                elif response.status_code == 404:
                    self.logger.info(f"DOI {doi} not found in CrossRef (404)")
                else:
                    self.logger.warning(f"CrossRef API returned status {response.status_code} for DOI {doi}")
                    
            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout while fetching bibliographic data for DOI {paper.doi}")
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Request error while fetching bibliographic data for DOI {paper.doi}: {str(e)}")
            except Exception as e:
                self.logger.warning(f"Unexpected error while fetching bibliographic data for DOI {paper.doi}: {str(e)}")
        elif paper.doi and not requests:
            self.logger.warning("Requests library not available, skipping CrossRef API call")
        
        # Try to extract from venue name if it contains volume/issue info
        if not any([volume_info['volume'], volume_info['issue'], volume_info['pages']]):
            if paper.venue:
                venue_lower = paper.venue.lower()
                
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
        
        # Format volume info for citation ONLY if we have real data
        if volume_info['volume']:
            if volume_info['issue']:
                return f"\\textbf{{{volume_info['volume']}}}({volume_info['issue']})"
            else:
                return f"\\textbf{{{volume_info['volume']}}}"
        
        # Return None if no real volume data found (don't use fake data)
        return None
    
    def _extract_page_numbers(self, paper: PaperMetadata) -> Optional[str]:
        """Extract page numbers using CrossRef API for accurate data."""
        # Try to get from CrossRef API if DOI is available
        if paper.doi and requests:
            try:
                import time
                
                # Clean DOI
                doi = paper.doi.strip()
                if doi.startswith('https://doi.org/'):
                    doi = doi.replace('https://doi.org/', '')
                elif doi.startswith('http://dx.doi.org/'):
                    doi = doi.replace('http://dx.doi.org/', '')
                elif doi.startswith('doi:'):
                    doi = doi.replace('doi:', '')
                
                # Query CrossRef API
                crossref_url = f"https://api.crossref.org/works/{doi}"
                headers = {
                    'User-Agent': 'Research System/1.0 (mailto:research@example.com)',
                    'Accept': 'application/json'
                }
                
                response = requests.get(crossref_url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    work = data.get('message', {})
                    
                    # Extract pages
                    if 'page' in work and work['page']:
                        pages = str(work['page']).strip()
                        if pages:
                            return pages
                    elif 'article-number' in work and work['article-number']:
                        article_num = str(work['article-number']).strip()
                        return article_num
                    
                    # Small delay for API
                    time.sleep(0.1)
                    
            except Exception as e:
                self.logger.warning(f"Error fetching page data from CrossRef for DOI {paper.doi}: {str(e)}")
        
        # Check if paper has pages attribute
        if hasattr(paper, 'pages') and paper.pages:
            return paper.pages
        
        # Return None if no real page data found (don't use fake data)
        return None
    
    def _format_doi(self, doi: str, url: str) -> Optional[str]:
        """Format DOI link."""
        if doi:
            if doi.startswith('http'):
                return doi
            else:
                return f"https://doi.org/{doi}"
        elif url:
            return url
        else:
            return None
    
    def _get_paper_url(self, paper: PaperMetadata) -> str:
        """Get the best URL for the paper."""
        if paper.doi:
            if paper.doi.startswith('http'):
                return paper.doi
            else:
                return f"https://doi.org/{paper.doi}"
        elif paper.url:
            return paper.url
        elif paper.arxiv_id:
            return f"https://arxiv.org/abs/{paper.arxiv_id}"
        else:
            return ""
    
    def _join_citation_parts(self, parts: List[str]) -> str:
        """Join citation parts with appropriate punctuation."""
        if not parts:
            return ""
        
        result = parts[0]  # Authors
        
        for i, part in enumerate(parts[1:], 1):
            if not part:
                continue
                
            if i == 1:  # Title
                result += f", {part}"
            elif i == 2:  # Venue
                result += f", {part}"
            elif i == 3:  # Volume
                result += f" {part}"
            elif i == 4:  # Year
                result += f" {part}"
            elif i == 5:  # Pages
                result += f" {part}"
            elif i == 6:  # DOI
                result += f". {part}"
            else:
                result += f", {part}"
        
        return result
    
    def _generate_paper_id(self, paper: PaperMetadata) -> str:
        """Generate unique paper ID (canonical, shared with claim/evidence extraction)."""
        return paper_id_for(paper)
    
    def filter_citations(self, citations: List[Dict[str, Any]], 
                        journal_filter: str = None, 
                        year_filter: int = None,
                        year_range: tuple = None) -> List[Dict[str, Any]]:
        """Filter citations by journal and year."""
        filtered = citations
        
        if journal_filter:
            filtered = [c for c in filtered 
                       if journal_filter.lower() in c['journal_name'].lower()]
        
        if year_filter:
            filtered = [c for c in filtered if c['year'] == year_filter]
        
        if year_range:
            start_year, end_year = year_range
            filtered = [c for c in filtered 
                       if start_year <= c['year'] <= end_year]
        
        return filtered
    
    def generate_bibliography(self, citations: List[Dict[str, Any]]) -> str:
        """Generate complete bibliography in LaTeX format."""
        if not citations:
            return ""
        
        bibliography = "\\begin{thebibliography}{99}\n\n"
        
        for citation in citations:
            bibliography += citation['bibitem_citation'] + "\n\n"
        
        bibliography += "\\end{thebibliography}"
        
        return bibliography
    
    def get_citation_stats(self, citations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about citations."""
        if not citations:
            return {"total": 0}
        
        journals = {}
        years = {}
        
        for citation in citations:
            journal = citation['journal_name']
            year = citation['year']
            
            journals[journal] = journals.get(journal, 0) + 1
            years[year] = years.get(year, 0) + 1
        
        return {
            "total_citations": len(citations),
            "unique_journals": len(journals),
            "year_range": f"{min(years.keys())}-{max(years.keys())}",
            "top_journals": sorted(journals.items(), key=lambda x: x[1], reverse=True)[:5],
            "year_distribution": dict(sorted(years.items()))
        }