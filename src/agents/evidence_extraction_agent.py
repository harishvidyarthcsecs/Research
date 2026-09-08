"""
Evidence Extraction Agent.

Wave 4 of the literature builder: extracts one structured EvidenceRow per paper
(population, method, dataset, metric, result, limitation) instead of feeding raw
abstracts straight to a paragraph-writing LLM call. This is the "evidence table"
the synthesis matrix and narrative generator are built from.

Same dual-mode convention as literature_builder_agent.py / research_gap_detection_agent.py:
EVIDENCE_MODE env var or constructor arg selects "llm" or "rules"; default auto-picks
"llm" iff a provider is configured.

Verbatim discipline: an LLM-proposed supporting_sentence is only trusted if it is an
actual substring of the paper's abstract. This mirrors the "LLM proposes, code
verifies" pattern journal_metadata.py established for quartiles — the LLM is not
trusted to invent facts that can be independently checked.

Grounding mode (GROUNDING_MODE env or constructor arg): "reject" (default) is the
build-time gate — a paraphrase-only LLM row is not admitted to the evidence table;
the caller falls back to deterministic rule extraction, and a rule row with no
signal is dropped entirely. "scored" keeps every row, attaching a grounding score
derived from how closely the supporting sentence matches the source. The two modes
are the A/B compared in the evaluation harness.
"""
import difflib
import json
import os
import re
from typing import List, Dict, Any, Optional
from collections import defaultdict

from ..models.data_models import PaperMetadata, Claim, EvidenceRow, TopicMap
from .base_agent import BaseAgent
from .paper_ids import paper_id_for
from . import llm_client

_POPULATION_RE = re.compile(
    r"(\d[\d,]*)\s+(participants|patients|subjects|students|samples|users|respondents)",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _substring_ratio(needle: str, haystack: str) -> float:
    """1.0 if `needle` is a (normalized) substring of `haystack`, else the best
    fuzzy overlap ratio. Used as the grounding score in scored mode."""
    n, h = _normalize(needle), _normalize(haystack)
    if not n or not h:
        return 0.0
    if n in h:
        return 1.0
    return difflib.SequenceMatcher(None, n, h).ratio()


def _best_metric(metrics: Dict[str, Any]) -> Optional[tuple]:
    """Pick one (metric_name, value) pair from a Claim.metrics dict, if any."""
    if not metrics:
        return None
    key = next(iter(metrics))
    return key, metrics[key]


class EvidenceExtractionAgent(BaseAgent):
    """Agent responsible for per-paper structured evidence extraction."""

    def __init__(self, memory_store=None, mode: Optional[str] = None,
                 grounding_mode: Optional[str] = None):
        super().__init__("EvidenceExtractionAgent", memory_store)
        self.mode = mode
        self.grounding_mode = grounding_mode
        self.tracker: Optional[llm_client.UsageTracker] = None

    def _resolve_mode(self) -> str:
        mode = self.mode or os.getenv("EVIDENCE_MODE")
        if mode in ("llm", "rules"):
            return mode
        return "llm" if llm_client.get_provider() is not None else "rules"

    def _resolve_grounding_mode(self) -> str:
        gm = self.grounding_mode or os.getenv("GROUNDING_MODE") or "reject"
        return gm if gm in ("reject", "scored") else "reject"

    async def process(self, papers: List[PaperMetadata], claims: List[Claim],
                       topic_map: Optional[TopicMap] = None) -> List[EvidenceRow]:
        mode = self._resolve_mode()
        grounding = self._resolve_grounding_mode()
        self.log_operation("evidence_extraction_start",
                           {"papers": len(papers), "mode": mode, "grounding": grounding})

        claims_by_paper: Dict[str, List[Claim]] = defaultdict(list)
        for c in claims:
            claims_by_paper[c.paper_id].append(c)

        rows: List[EvidenceRow] = []
        for paper in papers:
            pid = paper_id_for(paper)
            paper_claims = claims_by_paper.get(pid, [])
            row = None
            if mode == "llm":
                try:
                    row = self._llm_extract_one(paper, pid, paper_claims, grounding)
                except Exception as e:
                    self.logger.warning(f"LLM evidence extraction failed for {pid}: {e}; falling back to rules")
            if row is None:
                row = self._rules_extract_one(paper, pid, paper_claims, topic_map)
            rows.append(row)

        if grounding == "reject":
            # Build-time gate: a row only enters the evidence table if it carries
            # verbatim-verified support or deterministic rule-based signal. A
            # paraphrase-only LLM row was already turned into None above and
            # replaced by its rule row; here we drop rule rows with no signal so
            # nothing unverifiable propagates. Scored mode keeps everything.
            kept = [r for r in rows if r.verbatim_evidence or r.confidence > 0.0]
            self.log_operation("evidence_extraction_gate",
                               {"admitted": len(kept), "rejected": len(rows) - len(kept)})
            rows = kept

        await self.store_result("evidence_table", rows)
        self.log_operation("evidence_extraction_complete",
                           {"rows": len(rows), "mode": mode, "grounding": grounding})
        return rows

    # ------------------------------------------------------------------ #
    # LLM-based extraction                                                 #
    # ------------------------------------------------------------------ #

    def _llm_extract_one(self, paper: PaperMetadata, pid: str,
                          paper_claims: List[Claim],
                          grounding: str = "reject") -> Optional[EvidenceRow]:
        text = f"{paper.title}. {paper.abstract}"
        prompt = (
            "Extract structured evidence from this academic abstract for a systematic "
            "review evidence table. Output ONE JSON object with keys:\n"
            "  population (str or null): who/what was studied\n"
            "  method (str or null): the method/approach used\n"
            "  dataset (str or null): the dataset/benchmark used\n"
            "  metric (str or null): the evaluation metric name\n"
            "  result (str or null): a short scalar result, e.g. 'F1 0.87 (+4pp vs baseline)'\n"
            "  limitation (str or null): a stated limitation\n"
            "  supporting_sentence (str): the VERBATIM sentence from the text below that "
            "the result is drawn from — must be an exact substring, do not paraphrase\n"
            "Return ONLY the JSON object, nothing else.\n\n"
            f"Text:\n{text[:4000]}"
        )
        raw = llm_client.chat(
            prompt,
            max_tokens=400,
            temperature=0.0,
            tracker=self.tracker,
            purpose="evidence_extraction",
        ).strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        item = json.loads(raw)

        supporting = item.get("supporting_sentence") or ""
        ratio = _substring_ratio(supporting, paper.abstract or "")
        verified = bool(supporting) and _normalize(supporting) in _normalize(paper.abstract or "")

        if grounding == "reject" and not verified:
            # Unsupported paraphrase — do not admit it. The caller falls back to
            # deterministic rule extraction for this paper.
            return None

        return EvidenceRow(
            paper_id=pid,
            population=item.get("population") or None,
            method=item.get("method") or None,
            dataset=item.get("dataset") or None,
            metric=item.get("metric") or None,
            result=item.get("result") or None,
            limitation=item.get("limitation") or None,
            verbatim_evidence=supporting if verified else "",
            confidence=0.8 if verified else round(0.3 + 0.5 * ratio, 3),
            extraction_source="llm",
            claim_ids=[c.id for c in paper_claims],
        )

    # ------------------------------------------------------------------ #
    # Rules-based extraction (fallback)                                   #
    # ------------------------------------------------------------------ #

    def _rules_extract_one(self, paper: PaperMetadata, pid: str, paper_claims: List[Claim],
                            topic_map: Optional[TopicMap]) -> EvidenceRow:
        text = f"{paper.title}. {paper.abstract}"

        population = None
        m = _POPULATION_RE.search(text)
        if m:
            population = f"{m.group(1)} {m.group(2)}"

        method = None
        if topic_map:
            for candidate in topic_map.methods:
                if candidate.lower() in text.lower():
                    method = candidate
                    break

        dataset = None
        metric = None
        result = None
        limitation = None
        for c in paper_claims:
            if not dataset and c.datasets:
                dataset = c.datasets[0]
            if not metric or not result:
                best = _best_metric(c.metrics)
                if best:
                    metric, value = best
                    result = f"{metric} {value}"
            if not limitation and c.limitations:
                limitation = c.limitations[0]

        has_signal = any([population, method, dataset, metric, result, limitation])

        return EvidenceRow(
            paper_id=pid,
            population=population,
            method=method,
            dataset=dataset,
            metric=metric,
            result=result,
            limitation=limitation,
            verbatim_evidence="",
            confidence=0.5 if has_signal else 0.0,
            extraction_source="rules",
            claim_ids=[c.id for c in paper_claims],
        )
