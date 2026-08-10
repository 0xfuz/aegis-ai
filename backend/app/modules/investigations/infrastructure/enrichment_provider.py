"""
Enrichment provider abstraction for the IOC registry — mirrors the
ai_reasoning module's `LLMProvider` pattern (see
ai_reasoning/infrastructure/llm_provider.py): once a real external
threat-intel feed exists, the service layer would talk to
`EnrichmentProvider`, never to a specific vendor SDK. Adding one means a
new class here plus registering it in `get_enrichment_providers()` — not
a schema change, and not a change to `IOCRepository.set_enrichment`,
which already accepts whatever tags/confidence/verdict/enrichment a
provider (or a human analyst) produces, plus that provider's own
`provenance` key.

`get_enrichment_providers()` returning an empty list is deliberate, not a
placeholder waiting to be filled in by this change. Every `IOC.enrichment`
value in this codebase today came from seed-time manual curation or an
analyst action in the UI — `provenance="internal"` — never a real
external API call. Registering a fake provider here (or having the
frontend imply one was queried) would be exactly the kind of fabricated
result this project's AI-integrity rule forbids elsewhere. Wiring up the
first real provider (VirusTotal, AbuseIPDB, a commercial TI platform,
...) is future work, gated the same way ai_reasoning's LLM provider is
gated by config — not something this Phase 4 extension does.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EnrichmentResult:
    """What a provider hands back — shaped to drop straight into
    `IOCRepository.set_enrichment(ioc, tags=..., confidence=..., ...)`.
    `provenance` must be the provider's own key (e.g. "virustotal"),
    never "internal" — that value is reserved for seed/analyst curation
    and a provider implementation must not claim it."""

    tags: list[str]
    confidence: int
    verdict: str
    provenance: str
    enrichment: dict[str, Any] = field(default_factory=dict)


class EnrichmentProvider(ABC):
    """One external threat-intel source."""

    #: Must be unique across registered providers and never "internal".
    provenance_key: str

    @abstractmethod
    async def enrich(self, ioc_type: str, value: str) -> EnrichmentResult | None:
        """Look up one indicator against this provider. Returns None if
        the provider has no data for it — implementations must not
        fabricate a plausible-looking result just to avoid an empty
        state; an honest "no data" is what IOCService already falls back
        to today."""
        raise NotImplementedError


def get_enrichment_providers() -> list[EnrichmentProvider]:
    """Zero providers registered — see module docstring. A future
    provider gets instantiated and appended here, typically behind the
    same kind of environment-driven config switch `ai_reasoning` uses for
    AI_PROVIDER."""
    return []
