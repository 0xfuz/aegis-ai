"""
LLM provider abstraction. The service layer talks to `LLMProvider`, never
to a specific vendor SDK — swapping Anthropic for OpenAI (or adding a
second provider some orgs require for compliance reasons, per the
architecture doc) means a new class here, not a change anywhere else.

Deliberately implemented via raw HTTP (httpx, already a dependency) rather
than the Anthropic Python SDK, to avoid adding a heavy dependency for what
is, structurally, a single JSON-in/JSON-out call.
"""
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import get_settings
from app.shared.exceptions import AegisError

settings = get_settings()


class AIReasoningUnavailableError(AegisError):
    status_code = 503
    default_message = "AI reasoning isn't configured or is temporarily unavailable."


class LLMProvider(ABC):
    @abstractmethod
    async def complete_json(
        self, system_prompt: str, user_prompt: str, *, schema: dict[str, Any] | None = None,
        repair_response: str | None = None, validation_error: str | None = None,
    ) -> str:
        """Returns the raw text of the model's response. Callers are
        responsible for parsing/validating it as JSON — this layer only
        knows how to talk to the provider, not the reasoning schema."""
        raise NotImplementedError


class AnthropicProvider(LLMProvider):
    _API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def complete_json(self, system_prompt: str, user_prompt: str, **_kwargs: Any) -> str:
        if not self.api_key:
            raise AIReasoningUnavailableError(
                "AI reasoning isn't configured — set ANTHROPIC_API_KEY in the backend's .env to enable it."
            )

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    self._API_URL,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 1500,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": user_prompt}],
                    },
                )
            except httpx.RequestError as exc:
                raise AIReasoningUnavailableError(f"Couldn't reach the AI provider: {exc}") from exc

        if response.status_code != 200:
            raise AIReasoningUnavailableError(
                f"AI provider returned an error (HTTP {response.status_code}). "
                "Check ANTHROPIC_API_KEY is valid and has available credit."
            )

        data = response.json()
        content_blocks = data.get("content", [])
        text_blocks = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
        if not text_blocks:
            raise AIReasoningUnavailableError("AI provider returned an empty response.")
        return "".join(text_blocks)


class GeminiProvider(LLMProvider):
    """Google's Generative Language API — genuinely free within Gemini's
    per-minute/per-day rate limits (no credit card required to start),
    which is why it's the default provider rather than Anthropic. Uses
    Gemini's native JSON-mode response format so we don't have to strip
    markdown fences the way a plain-text prompt sometimes requires."""

    _API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def complete_json(self, system_prompt: str, user_prompt: str, **_kwargs: Any) -> str:
        if not self.api_key:
            raise AIReasoningUnavailableError(
                "AI reasoning isn't configured — set GEMINI_API_KEY in the backend's .env to enable it."
            )

        url = self._API_URL_TEMPLATE.format(model=self.model)

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    url,
                    params={"key": self.api_key},
                    headers={"content-type": "application/json"},
                    json={
                        "system_instruction": {"parts": [{"text": system_prompt}]},
                        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                        "generationConfig": {
                            "temperature": 0.4,
                            "maxOutputTokens": 1500,
                            "responseMimeType": "application/json",
                        },
                    },
                )
            except httpx.RequestError as exc:
                raise AIReasoningUnavailableError(f"Couldn't reach the AI provider: {exc}") from exc

        if response.status_code != 200:
            raise AIReasoningUnavailableError(
                f"AI provider returned an error (HTTP {response.status_code}): {response.text[:500]}"
            )

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            # Usually means the response was blocked by Gemini's safety
            # filters rather than a transport error — worth surfacing
            # distinctly rather than a generic "empty response".
            reason = data.get("promptFeedback", {}).get("blockReason")
            if reason:
                raise AIReasoningUnavailableError(f"AI provider blocked this request (reason: {reason}).")
            raise AIReasoningUnavailableError("AI provider returned no candidates.")

        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [p.get("text", "") for p in parts if "text" in p]
        if not text_parts:
            raise AIReasoningUnavailableError("AI provider returned an empty response.")
        return "".join(text_parts)


class OllamaProvider(LLMProvider):
    """Runs entirely on your own hardware via Ollama — no API key, no
    billing account, no regional eligibility restrictions of any kind,
    since nothing leaves your machine. The trade-off is quality (a small
    local model reasons noticeably worse than Gemini/Claude) and speed
    (especially without a GPU). This is the option that's guaranteed to
    work regardless of what country the free cloud tiers are or aren't
    available in."""

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def complete_json(
        self, system_prompt: str, user_prompt: str, *, schema: dict[str, Any] | None = None,
        repair_response: str | None = None, validation_error: str | None = None,
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if repair_response is not None and validation_error is not None:
            messages.append({
                "role": "user",
                "content": (
                    "Repair the prior response below. Return only one complete JSON object that conforms "
                    "exactly to the schema and uses only FACT IDs from the original canonical context. "
                    f"Validation errors: {validation_error}. Prior response: {repair_response}"
                ),
            })
        async with httpx.AsyncClient(timeout=120.0) as client:  # local inference can be slow, especially on CPU
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "format": schema or "json",
                        "stream": False,
                        "options": {"temperature": 0},
                    },
                )
            except httpx.RequestError as exc:
                raise AIReasoningUnavailableError(
                    f"Couldn't reach Ollama at {self.base_url}: {exc}. "
                    "Is the ollama container running, and has the model been pulled?"
                ) from exc

        if response.status_code != 200:
            raise AIReasoningUnavailableError(
                f"Ollama returned an error (HTTP {response.status_code}): {response.text[:500]}"
            )

        data = response.json()
        text = data.get("message", {}).get("content", "")
        if not text:
            raise AIReasoningUnavailableError("Ollama returned an empty response.")
        return text


def get_llm_provider() -> LLMProvider:
    """Single place that decides which provider backs the app. Switch via
    settings.AI_PROVIDER ('gemini' | 'anthropic' | 'ollama') — nothing
    else in the module changes when adding a fourth vendor, just another
    branch here."""
    if settings.AI_PROVIDER == "anthropic":
        return AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY, model=settings.ANTHROPIC_MODEL)
    if settings.AI_PROVIDER == "ollama":
        return OllamaProvider(base_url=settings.OLLAMA_BASE_URL, model=settings.OLLAMA_MODEL)
    return GeminiProvider(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)
