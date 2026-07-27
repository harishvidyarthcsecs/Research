"""
Unified LLM client with automatic fallback and usage/cost tracking.

Priority order:
  1. xAI Grok          — if XAI_API_KEY is set
  2. Anthropic Claude  — if ANTHROPIC_API_KEY is set
  3. Groq              — if GROQ_API_KEY is set (free tier: llama-3.3-70b)
  4. Ollama (local)    — if ollama is running at OLLAMA_HOST (default localhost:11434)
  5. OpenRouter        — if OPENROUTER_API_KEY is set

Set LLM_PROVIDER to one of "xai" / "anthropic" / "groq" / "ollama" / "openrouter"
to pin a provider (used for reproducible evaluation runs).
"""
from __future__ import annotations
import os
import threading
from typing import Optional, Tuple, Dict

import requests


# Default models for each provider
DEFAULTS = {
    "xai":       "grok-3-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "groq":      "llama-3.3-70b-versatile",
    "ollama":    os.getenv("OLLAMA_MODEL", "llama3.2"),
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
}

# USD per million tokens (input, output). Local/free-tier models cost 0.
PRICING = {
    "grok-3-mini": (0.30, 0.50),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "meta-llama/llama-3.3-70b-instruct:free": (0.0, 0.0),
}

Usage = Dict[str, int]  # {"prompt_tokens": int, "completion_tokens": int}


class UsageTracker:
    """Thread-safe accumulator of LLM token usage and estimated cost for one run."""

    def __init__(self):
        self._lock = threading.Lock()
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.estimated_cost_usd = 0.0
        self.parse_failures = 0
        self.by_purpose: Dict[str, Dict[str, float]] = {}

    def record(self, provider: str, model: str, prompt_tokens: int,
               completion_tokens: int, purpose: str = "general") -> None:
        in_rate, out_rate = PRICING.get(model, (0.0, 0.0))
        cost = (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000
        with self._lock:
            self.calls += 1
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
            self.estimated_cost_usd += cost
            slot = self.by_purpose.setdefault(purpose, {
                "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                "estimated_cost_usd": 0.0, "parse_failures": 0,
            })
            slot["calls"] += 1
            slot["prompt_tokens"] += prompt_tokens
            slot["completion_tokens"] += completion_tokens
            slot["estimated_cost_usd"] += cost

    def record_parse_failure(self, purpose: str = "general") -> None:
        with self._lock:
            self.parse_failures += 1
            slot = self.by_purpose.setdefault(purpose, {
                "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                "estimated_cost_usd": 0.0, "parse_failures": 0,
            })
            slot["parse_failures"] += 1

    def summary(self) -> dict:
        with self._lock:
            return {
                "calls": self.calls,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "estimated_cost_usd": round(self.estimated_cost_usd, 6),
                "parse_failures": self.parse_failures,
                "by_purpose": {
                    k: {**v, "estimated_cost_usd": round(v["estimated_cost_usd"], 6)}
                    for k, v in self.by_purpose.items()
                },
            }


def _openai_style_usage(data: dict) -> Usage:
    usage = data.get("usage") or {}
    return {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
    }


def _xai_chat(prompt: str, max_tokens: int, temperature: float) -> Tuple[str, Usage]:
    resp = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.environ['XAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "model": DEFAULTS["xai"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"], _openai_style_usage(data)


def _anthropic_chat(prompt: str, max_tokens: int, temperature: float) -> Tuple[str, Usage]:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=DEFAULTS["anthropic"],
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    usage = {
        "prompt_tokens": int(getattr(msg.usage, "input_tokens", 0) or 0),
        "completion_tokens": int(getattr(msg.usage, "output_tokens", 0) or 0),
    }
    return msg.content[0].text, usage


def _groq_chat(prompt: str, max_tokens: int, temperature: float) -> Tuple[str, Usage]:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.environ['GROQ_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "model": DEFAULTS["groq"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"], _openai_style_usage(data)


def _ollama_chat(prompt: str, max_tokens: int, temperature: float) -> Tuple[str, Usage]:
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = DEFAULTS["ollama"]
    resp = requests.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = {
        "prompt_tokens": int(data.get("prompt_eval_count") or 0),
        "completion_tokens": int(data.get("eval_count") or 0),
    }
    return data["message"]["content"], usage


def _openrouter_chat(prompt: str, max_tokens: int, temperature: float) -> Tuple[str, Usage]:
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5001",
        },
        json={
            "model": DEFAULTS["openrouter"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"], _openai_style_usage(data)


_PROVIDER_FUNCS = {
    "xai": _xai_chat,
    "anthropic": _anthropic_chat,
    "groq": _groq_chat,
    "ollama": _ollama_chat,
    "openrouter": _openrouter_chat,
}

_PROVIDER_KEYS = {
    "xai": "XAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _ollama_available() -> bool:
    """Check if Ollama is running locally."""
    try:
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        resp = requests.get(f"{host}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = [m["name"].split(":")[0] for m in resp.json().get("models", [])]
            preferred = DEFAULTS["ollama"].split(":")[0]
            if models:
                # Use preferred model if available, else first available
                if preferred not in models:
                    DEFAULTS["ollama"] = models[0]
                return True
    except Exception:
        pass
    return False


def get_provider() -> str | None:
    """Return the active LLM provider.

    Honors an explicit LLM_PROVIDER pin (for reproducible eval runs); otherwise
    returns the first provider whose credentials are available.
    """
    pinned = os.getenv("LLM_PROVIDER")
    if pinned:
        pinned = pinned.strip().lower()
        if pinned == "ollama":
            return "ollama" if _ollama_available() else None
        if pinned in _PROVIDER_KEYS and os.getenv(_PROVIDER_KEYS[pinned]):
            return pinned
        return None
    if os.getenv("XAI_API_KEY"):
        return "xai"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if _ollama_available():
        return "ollama"
    if os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    return None


def chat(prompt: str, max_tokens: int = 2000, temperature: float = 0.3,
         tracker: Optional[UsageTracker] = None, purpose: str = "general") -> str:
    """
    Send a prompt and return the response text.
    Automatically uses the first available provider (or the LLM_PROVIDER pin).
    Records token usage into `tracker` when provided.
    Raises RuntimeError if no provider is available.
    """
    provider = get_provider()
    func = _PROVIDER_FUNCS.get(provider)
    if func is None:
        raise RuntimeError(
            "No LLM available. Options:\n"
            "  • Set XAI_API_KEY (xAI Grok — console.x.ai)\n"
            "  • Set ANTHROPIC_API_KEY\n"
            "  • Set GROQ_API_KEY (free at console.groq.com)\n"
            "  • Run Ollama locally: ollama serve && ollama pull llama3.2\n"
            "  • Set OPENROUTER_API_KEY (free tier at openrouter.ai)"
        )
    text, usage = func(prompt, max_tokens, temperature)
    if tracker is not None:
        tracker.record(
            provider=provider,
            model=DEFAULTS[provider],
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            purpose=purpose,
        )
    return text


def provider_info() -> dict:
    """Return info about the active provider for the status page."""
    provider = get_provider()
    labels = {
        "xai":       ("xAI Grok",          DEFAULTS["xai"]),
        "anthropic": ("Anthropic Claude",   DEFAULTS["anthropic"]),
        "groq":      ("Groq (free)",        DEFAULTS["groq"]),
        "ollama":    ("Ollama (local)",     DEFAULTS["ollama"]),
        "openrouter":("OpenRouter (free)",  DEFAULTS["openrouter"]),
    }
    if provider:
        name, model = labels[provider]
        return {"available": True, "provider": provider, "name": name, "model": model}
    return {"available": False, "provider": None, "name": "None", "model": ""}
