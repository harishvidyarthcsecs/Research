"""
AI Writing Humanizer Agent.
Accepts extracted text and uses Claude to remove AI writing patterns,
producing natural prose based on the humanizer skill guidelines.
"""
import os
import re
import json
from typing import Optional


HUMANIZER_SYSTEM = """You are an expert writing editor. Your job is to transform AI-generated academic text into natural, human-sounding prose.

Remove these AI writing patterns:
- Inflated significance claims ("pivotal", "testament", "underscores", "highlights")
- Promotional language ("vibrant", "breathtaking", "nestled", "groundbreaking")
- Superficial -ing endings ("showcasing", "fostering", "reflecting deeper meaning")
- Vague attributions ("experts argue", "industry observers note")
- Em dash overuse — replace with commas or periods
- Rule of three padding (lists of exactly three items for no reason)
- AI vocabulary ("delve", "crucial", "landscape", "tapestry", "interplay", "pivotal")
- Passive voice hiding the actor
- Negative parallelisms ("not just X, but Y")
- Filler phrases ("in order to", "due to the fact that", "it is important to note that")
- Sycophantic openers ("Great question!", "Certainly!", "Of course!")
- Title Case In Every Heading
- Inline header bullet lists with **Bold:** followed by a colon
- Overused boldface
- Signposting ("Let's dive in", "Here's what you need to know")

Replace these with:
- Direct, specific sentences
- Active voice with clear actors
- Concrete details over vague claims
- Natural sentence rhythm (mix short and long)
- First person where appropriate
- Honest acknowledgment of uncertainty

Return ONLY the humanized text, no meta-commentary."""


class HumanizerAgent:
    """Humanizes AI-generated writing using Claude."""

    def __init__(self):
        self._client = None
        self._available = bool(os.environ.get("ANTHROPIC_API_KEY"))

    def _get_client(self):
        if self._client is None and self._available:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            except ImportError:
                self._available = False
        return self._client

    def humanize(self, text: str, context: str = "academic") -> dict:
        """
        Humanize text. Returns dict with keys:
          original, draft, audit_notes, final, method
        """
        client = self._get_client()
        if client is None:
            return {
                "original": text,
                "draft": text,
                "audit_notes": "LLM unavailable — set ANTHROPIC_API_KEY to enable humanization.",
                "final": text,
                "method": "passthrough",
            }

        # Stage 1: Draft humanization
        draft = self._call_llm(client, HUMANIZER_SYSTEM, text)

        # Stage 2: Self-audit
        audit_prompt = (
            "What makes the following text still obviously AI-generated? "
            "List only the remaining tells as short bullet points.\n\n" + draft
        )
        audit_notes = self._call_llm(
            client,
            "You are a writing critic. Identify remaining AI writing patterns concisely.",
            audit_prompt,
        )

        # Stage 3: Final revision
        final_prompt = (
            "Revise the text below to fix these remaining AI writing patterns:\n"
            f"{audit_notes}\n\nText:\n{draft}"
        )
        final = self._call_llm(client, HUMANIZER_SYSTEM, final_prompt)

        return {
            "original": text,
            "draft": draft,
            "audit_notes": audit_notes,
            "final": final,
            "method": "claude",
        }

    def _call_llm(self, client, system: str, user_text: str) -> str:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user_text}],
        )
        return response.content[0].text.strip()
