"""
AI Writing Humanizer Agent.
Accepts extracted text and uses any available LLM (Anthropic, Groq, Ollama, OpenRouter)
to remove AI writing patterns, producing natural prose.
"""
import os
from src.agents.llm_client import chat, provider_info, get_provider


HUMANIZER_SYSTEM = """You are an expert writing editor. Transform AI-generated academic text into natural, human-sounding prose.

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

Replace with:
- Direct, specific sentences
- Active voice with clear actors
- Concrete details over vague claims
- Natural sentence rhythm (mix short and long)
- First person where appropriate
- Honest acknowledgment of uncertainty

Return ONLY the humanized text, no meta-commentary."""


class HumanizerAgent:
    """Humanizes AI-generated writing using any available LLM."""

    def humanize(self, text: str, context: str = "academic") -> dict:
        """
        Humanize text. Returns dict with keys:
          original, draft, audit_notes, final, method, provider
        """
        info = provider_info()
        if not info["available"]:
            return {
                "original": text,
                "draft": text,
                "audit_notes": (
                    "No LLM available. To enable humanization:\n"
                    "• Set ANTHROPIC_API_KEY (get one at console.anthropic.com)\n"
                    "• Set GROQ_API_KEY — free at console.groq.com (fast Llama 3.3 70B)\n"
                    "• Run Ollama locally: brew install ollama && ollama serve && ollama pull llama3.2\n"
                    "• Set OPENROUTER_API_KEY — free tier at openrouter.ai"
                ),
                "final": text,
                "method": "passthrough",
                "provider": None,
            }

        provider = info["provider"]

        # Stage 1: Draft humanization
        draft = self._call(f"{HUMANIZER_SYSTEM}\n\nText to humanize:\n{text}")

        # Stage 2: Self-audit
        audit_prompt = (
            "What makes the following text still obviously AI-generated? "
            "List only the remaining tells as short bullet points.\n\n" + draft
        )
        audit_notes = self._call(audit_prompt, max_tokens=800)

        # Stage 3: Final revision
        final_prompt = (
            f"{HUMANIZER_SYSTEM}\n\n"
            f"Fix these remaining AI writing patterns in the text:\n{audit_notes}\n\nText:\n{draft}"
        )
        final = self._call(final_prompt)

        return {
            "original": text,
            "draft": draft,
            "audit_notes": audit_notes,
            "final": final,
            "method": provider,
            "provider": info["name"],
        }

    def _call(self, prompt: str, max_tokens: int = 3000) -> str:
        try:
            return chat(prompt, max_tokens=max_tokens).strip()
        except Exception as e:
            return f"[LLM error: {e}]"
