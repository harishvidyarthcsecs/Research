"""Systematic review abstract screener using any available LLM."""
import os
import json
import re
from src.agents.llm_client import chat, provider_info


class AbstractScreenerAgent:
    def __init__(self):
        info = provider_info()
        if not info["available"]:
            raise RuntimeError(
                "No LLM available for abstract screening.\n"
                "Options: ANTHROPIC_API_KEY, GROQ_API_KEY, Ollama (ollama serve), or OPENROUTER_API_KEY"
            )

    def _screen_batch(self, abstracts: list, criteria: str, batch_start: int) -> list:
        abstract_block = []
        for i, ab in enumerate(abstracts):
            num = batch_start + i + 1
            title = ab.get("title", f"Paper {num}")
            text = ab.get("abstract", ab.get("text", ""))
            abstract_block.append(f"[{num}] TITLE: {title}\nABSTRACT: {text[:500]}")

        prompt = f"""You are a systematic review expert applying PRISMA guidelines. Screen each abstract against the provided criteria.

INCLUSION/EXCLUSION CRITERIA:
{criteria}

ABSTRACTS TO SCREEN:
{chr(10).join(abstract_block)}

For each abstract decide INCLUDE, MAYBE, or EXCLUDE.

Return ONLY a JSON array:
[
  {{
    "paper_number": 1,
    "decision": "INCLUDE",
    "confidence": 90,
    "reasoning": "Brief explanation",
    "matched_criteria": ["criterion"],
    "concerns": ""
  }}
]"""

        try:
            raw = chat(prompt, max_tokens=3000).strip()
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            print(f"Screening batch error: {e}")
        return []

    def screen(self, abstracts: list, criteria: str) -> dict:
        if not abstracts:
            return {"error": "No abstracts provided", "results": []}

        all_results = []
        for i in range(0, len(abstracts), 10):
            batch = abstracts[i:i + 10]
            all_results.extend(self._screen_batch(batch, criteria, i))

        final_results = []
        for r in all_results:
            num = r.get("paper_number", 1)
            idx = num - 1
            original = abstracts[idx] if 0 <= idx < len(abstracts) else {}
            final_results.append({
                "paper_number": num,
                "title": original.get("title", f"Paper {num}"),
                "decision": r.get("decision", "MAYBE"),
                "confidence": r.get("confidence", 50),
                "reasoning": r.get("reasoning", ""),
                "matched_criteria": r.get("matched_criteria", []),
                "concerns": r.get("concerns", ""),
            })

        include_count = sum(1 for r in final_results if r["decision"] == "INCLUDE")
        maybe_count   = sum(1 for r in final_results if r["decision"] == "MAYBE")
        exclude_count = sum(1 for r in final_results if r["decision"] == "EXCLUDE")

        return {
            "total": len(abstracts),
            "include_count": include_count,
            "maybe_count": maybe_count,
            "exclude_count": exclude_count,
            "results": final_results,
            "summary": f"{include_count} included, {maybe_count} uncertain, {exclude_count} excluded out of {len(abstracts)} abstracts.",
        }
