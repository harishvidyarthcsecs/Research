"""Pre-submission checklist generator using any available LLM + OpenAlex."""
import os
import re
import json
import requests
from src.agents.llm_client import chat, provider_info


class ChecklistAgent:
    def __init__(self):
        info = provider_info()
        if not info["available"]:
            raise RuntimeError(
                "No LLM available for checklist generation.\n"
                "Options: ANTHROPIC_API_KEY, GROQ_API_KEY, Ollama (ollama serve), or OPENROUTER_API_KEY"
            )
        self.openalex_base = "https://api.openalex.org"
        self.headers = {"User-Agent": "ResearchAgent/1.0 (mailto:research@example.com)"}

    def _fetch_journal_info(self, journal_name: str) -> dict:
        try:
            resp = requests.get(
                f"{self.openalex_base}/sources",
                params={
                    "search": journal_name,
                    "filter": "type:journal",
                    "per-page": 1,
                },
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    return results[0]
        except Exception as e:
            print(f"OpenAlex journal fetch error: {e}")
        return {}

    def generate(self, manuscript_type: str, journal: str, field: str, abstract: str = "") -> dict:
        journal_info = self._fetch_journal_info(journal) if journal else {}

        ss = journal_info.get("summary_stats") or {}
        journal_context = f"Target Journal: {journal_info.get('display_name', journal or 'Not specified')}"
        if journal_info:
            journal_context += f"\nPublisher: {journal_info.get('host_organization_name', '')}"
            journal_context += f"\nH-index: {ss.get('h_index', 'N/A')}"
            journal_context += f"\nImpact factor: {round(ss.get('2yr_mean_citedness', 0) or 0, 2)}"

        abstract_context = f"\nPaper Abstract:\n{abstract[:400]}" if abstract else ""

        prompt = f"""Generate a comprehensive pre-submission checklist for:
- Manuscript Type: {manuscript_type}
- Field: {field or 'General'}
- {journal_context}{abstract_context}

Organize into categories. For each item specify CRITICAL, IMPORTANT, or RECOMMENDED.

Return ONLY a JSON object:
{{
  "categories": [
    {{
      "name": "Manuscript Structure & Formatting",
      "icon": "fas fa-file-alt",
      "color": "blue",
      "items": [
        {{
          "text": "Title is concise and informative",
          "priority": "CRITICAL",
          "description": "Avoid abbreviations in the title"
        }}
      ]
    }}
  ],
  "journal_tips": ["Tip 1", "Tip 2"],
  "estimated_review_time": "4-8 weeks"
}}

Category icons to use:
- Structure: fas fa-file-alt (color: blue)
- Content Quality: fas fa-microscope (color: purple)
- References: fas fa-quote-right (color: orange)
- Figures & Data: fas fa-chart-bar (color: green)
- Ethics: fas fa-shield-alt (color: red)
- Cover Letter: fas fa-envelope (color: blue)
- Journal Requirements: fas fa-bullseye (color: orange)"""

        try:
            raw = chat(prompt, max_tokens=3000).strip()
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                data["journal_info"] = {
                    "name": journal_info.get("display_name", journal),
                    "publisher": journal_info.get("host_organization_name", ""),
                    "h_index": ss.get("h_index"),
                    "homepage": journal_info.get("homepage_url", ""),
                }
                return data
        except Exception as e:
            print(f"Checklist generation error: {e}")

        return {"error": "Failed to generate checklist", "categories": []}
