"""
Paper Reading & Claim Extraction Agent.
Uses the shared LLM client (any configured provider) for robust extraction,
falls back to regex when no provider is available.
"""
import re
import json
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..models.data_models import PaperMetadata, Claim
from .base_agent import BaseAgent
from . import llm_client


class ClaimExtractionAgent(BaseAgent):
    """Agent responsible for reading papers and extracting structured claims."""

    def __init__(self, memory_store=None):
        super().__init__("ClaimExtractionAgent", memory_store)
        self.tracker: Optional[llm_client.UsageTracker] = None
        self._use_llm = llm_client.get_provider() is not None

    async def process(self, papers: List[PaperMetadata]) -> List[Claim]:
        self.log_operation("claim_extraction_start", {"paper_count": len(papers)})

        semaphore = asyncio.Semaphore(5)
        tasks = [self._extract_claims_from_paper(paper, semaphore) for paper in papers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_claims: List[Claim] = []
        for result in results:
            if isinstance(result, list):
                all_claims.extend(result)
            elif isinstance(result, Exception):
                self.logger.error(f"Error processing paper: {result}")

        await self.store_result("extracted_claims", all_claims)
        self.log_operation("claim_extraction_complete", {
            "total_claims": len(all_claims),
            "papers_processed": len([r for r in results if isinstance(r, list)]),
            "method": "llm" if self._use_llm else "regex",
        })
        return all_claims

    async def _extract_claims_from_paper(self, paper: PaperMetadata, semaphore: asyncio.Semaphore) -> List[Claim]:
        async with semaphore:
            paper_id = self._generate_paper_id(paper)
            text = f"{paper.title}. {paper.abstract}"

            if self._use_llm:
                return await asyncio.get_event_loop().run_in_executor(
                    None, self._llm_extract, text, paper_id, paper
                )
            return self._regex_extract(text, paper_id, paper)

    # ------------------------------------------------------------------ #
    # LLM-based extraction                                                 #
    # ------------------------------------------------------------------ #

    def _llm_extract(self, text: str, paper_id: str, paper: PaperMetadata) -> List[Claim]:
        prompt = (
            "Extract all scientific claims from the following academic text. "
            "For each claim output a JSON object with keys:\n"
            "  statement (str), claim_type (str), confidence (0.0-1.0), "
            "metrics (dict of metric_name->value), datasets (list of str), "
            "conditions (list of str), limitations (list of str), "
            "evidence_sentence (str: the verbatim sentence from the text that "
            "the claim is based on).\n"
            "Return ONLY a JSON array, nothing else.\n\n"
            f"Text:\n{text[:4000]}"
        )

        try:
            raw = llm_client.chat(
                prompt,
                max_tokens=2048,
                temperature=0.0,
                tracker=self.tracker,
                purpose="claim_extraction",
            ).strip()
            # Strip markdown code fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            items = json.loads(raw)
            claims = []
            for item in items:
                claim_id = f"{paper_id}_llm_{datetime.now().timestamp()}_{len(claims)}"
                evidence = item.get("evidence_sentence") or item.get("statement", "")
                claims.append(Claim(
                    id=claim_id,
                    statement=item.get("statement", ""),
                    paper_id=paper_id,
                    evidence=[evidence],
                    metrics=item.get("metrics", {}),
                    confidence=float(item.get("confidence", 0.7)),
                    datasets=item.get("datasets", []),
                    conditions=item.get("conditions", []),
                    limitations=item.get("limitations", []),
                ))
            return claims
        except json.JSONDecodeError as e:
            if self.tracker is not None:
                self.tracker.record_parse_failure("claim_extraction")
            self.logger.warning(f"LLM extraction failed for {paper_id}: {e}; falling back to regex")
            return self._regex_extract(text, paper_id, paper)
        except Exception as e:
            self.logger.warning(f"LLM extraction failed for {paper_id}: {e}; falling back to regex")
            return self._regex_extract(text, paper_id, paper)

    # ------------------------------------------------------------------ #
    # Regex-based extraction (fallback)                                    #
    # ------------------------------------------------------------------ #

    _CLAIM_PATTERNS = [
        {"pattern": r"(improves?|increases?|reduces?|decreases?|achieves?|outperforms?)\s+.*?by\s+(\d+(?:\.\d+)?)\s*(%|percent|points?)", "type": "performance_improvement", "confidence": 0.9},
        {"pattern": r"(accuracy|precision|recall|f1-score|auc)\s+of\s+(\d+(?:\.\d+)?)\s*(%|percent)?", "type": "metric_achievement", "confidence": 0.8},
        {"pattern": r"(significantly|substantially|considerably)\s+(better|worse|higher|lower|improved)", "type": "comparative_claim", "confidence": 0.7},
        {"pattern": r"(state-of-the-art|sota|best|superior|novel|first)", "type": "novelty_claim", "confidence": 0.6},
    ]

    _METRIC_PATTERNS = [
        {"pattern": r"accuracy[:\s]+(\d+(?:\.\d+)?)\s*(%|percent)?", "metric": "accuracy"},
        {"pattern": r"precision[:\s]+(\d+(?:\.\d+)?)\s*(%|percent)?", "metric": "precision"},
        {"pattern": r"recall[:\s]+(\d+(?:\.\d+)?)\s*(%|percent)?", "metric": "recall"},
        {"pattern": r"f1[-\s]score[:\s]+(\d+(?:\.\d+)?)\s*(%|percent)?", "metric": "f1_score"},
        {"pattern": r"auc[:\s]+(\d+(?:\.\d+)?)", "metric": "auc"},
        {"pattern": r"rmse[:\s]+(\d+(?:\.\d+)?)", "metric": "rmse"},
        {"pattern": r"mae[:\s]+(\d+(?:\.\d+)?)", "metric": "mae"},
    ]

    def _regex_extract(self, text: str, paper_id: str, paper: PaperMetadata) -> List[Claim]:
        claims = []
        sentences = re.split(r"[.!?]+", text)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            for pat_info in self._CLAIM_PATTERNS:
                if re.search(pat_info["pattern"], sentence, re.IGNORECASE):
                    claim_id = f"{paper_id}_regex_{len(claims)}_{datetime.now().timestamp()}"
                    claims.append(Claim(
                        id=claim_id,
                        statement=sentence,
                        paper_id=paper_id,
                        evidence=[sentence],
                        metrics=self._extract_metrics(sentence),
                        confidence=pat_info["confidence"],
                        datasets=self._extract_datasets(text),
                        conditions=self._extract_conditions(sentence),
                        limitations=self._extract_limitations(text),
                    ))
                    break
        return claims

    def _extract_metrics(self, sentence: str) -> Dict[str, Any]:
        metrics = {}
        for pat in self._METRIC_PATTERNS:
            m = re.search(pat["pattern"], sentence, re.IGNORECASE)
            if m:
                try:
                    metrics[pat["metric"]] = float(m.group(1))
                except (ValueError, IndexError):
                    pass
        return metrics

    def _extract_datasets(self, text: str) -> List[str]:
        patterns = [
            r"\b(MNIST|CIFAR-10|CIFAR-100|ImageNet|COCO|Pascal VOC)\b",
            r"\b(ChEMBL|PubChem|DrugBank|ZINC|QM9)\b",
            r"\b(Cora|CiteSeer|PubMed|Reddit|OGB)\b",
            r"\b(GLUE|SQuAD|CoNLL|WikiText)\b",
        ]
        found = set()
        for p in patterns:
            for m in re.finditer(p, text, re.IGNORECASE):
                found.add(m.group(0))
        return list(found)

    def _extract_conditions(self, sentence: str) -> List[str]:
        conditions = []
        for pat in [r"under\s+([^.,;]+)", r"with\s+([^.,;]+)", r"using\s+([^.,;]+)"]:
            for m in re.finditer(pat, sentence, re.IGNORECASE):
                cond = m.group(1).strip()
                if len(cond) < 100:
                    conditions.append(cond)
        return conditions

    def _extract_limitations(self, text: str) -> List[str]:
        keywords = {"limitation", "limited", "constraint", "drawback", "weakness", "shortcoming"}
        limitations = []
        for sentence in re.split(r"[.!?]+", text):
            if any(kw in sentence.lower() for kw in keywords):
                limitations.append(sentence.strip())
        return limitations

    def _generate_paper_id(self, paper: PaperMetadata) -> str:
        if paper.doi:
            return paper.doi.replace("/", "_").replace(".", "_")
        if paper.arxiv_id:
            return f"arxiv_{paper.arxiv_id}"
        words = re.findall(r"\w+", paper.title.lower())[:5]
        return f"{'_'.join(words)}_{paper.year}"
