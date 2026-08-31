"""Phase 8.5 trusted, non-persistent provider boundary."""
from __future__ import annotations
import ipaddress
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from threading import BoundedSemaphore
from typing import Callable, Protocol
from urllib.parse import urlsplit
import httpx
from app.core.config import get_settings

PROTOCOL_VERSION="intelligence-run-v1"
PROMPT_VERSION="intelligence-evidence-grounded-v1"
CANDIDATE_SCHEMA_VERSION="intelligence-candidate-output-v1"
_MODEL_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}(?::[a-z0-9][a-z0-9._-]{0,127})?$")

class ProviderCategory(StrEnum):
    DISABLED="PROVIDER_DISABLED"; MISCONFIGURED="PROVIDER_MISCONFIGURED"; UNAVAILABLE="PROVIDER_UNAVAILABLE"; MODEL_UNAVAILABLE="PROVIDER_MODEL_UNAVAILABLE"; TIMEOUT="PROVIDER_TIMEOUT"; RESPONSE_TOO_LARGE="PROVIDER_RESPONSE_TOO_LARGE"; PROTOCOL_ERROR="PROVIDER_PROTOCOL_ERROR"; CANCELLED="PROVIDER_CANCELLED"; CONCURRENCY_LIMIT="PROVIDER_CONCURRENCY_LIMIT"; INTERNAL="PROVIDER_INTERNAL"
class ProviderFailure(Exception):
    def __init__(self, category: ProviderCategory): self.category=category; super().__init__(category.value)
class ReadinessState(StrEnum): READY="READY"; DISABLED="DISABLED"; UNAVAILABLE="UNAVAILABLE"; MISCONFIGURED="MISCONFIGURED"

@dataclass(frozen=True)
class ProviderPolicy:
    provider: str; base_url: str; model: str; allowed_models: tuple[str,...]; connect_timeout_seconds:int; read_timeout_seconds:int; total_timeout_seconds:int; max_request_bytes:int; max_response_bytes:int; max_concurrency:int
    @classmethod
    def from_settings(cls, settings=None):
        s=settings or get_settings(); allowed=tuple(item.strip() for item in s.INTELLIGENCE_OLLAMA_ALLOWED_MODELS.split(",") if item.strip())
        return cls(s.INTELLIGENCE_PROVIDER,s.INTELLIGENCE_OLLAMA_BASE_URL,s.INTELLIGENCE_OLLAMA_MODEL,allowed,s.INTELLIGENCE_PROVIDER_CONNECT_TIMEOUT_SECONDS,s.INTELLIGENCE_PROVIDER_READ_TIMEOUT_SECONDS,s.INTELLIGENCE_PROVIDER_TOTAL_TIMEOUT_SECONDS,s.INTELLIGENCE_PROVIDER_MAX_REQUEST_BYTES,s.INTELLIGENCE_PROVIDER_MAX_RESPONSE_BYTES,s.INTELLIGENCE_PROVIDER_MAX_CONCURRENCY)
    def __post_init__(self):
        if self.provider != "ollama" or not self.allowed_models or self.model not in self.allowed_models or not _MODEL_NAME.fullmatch(self.model) or any(not _MODEL_NAME.fullmatch(value) for value in self.allowed_models): raise ValueError("Invalid intelligence provider policy.")
        if min(self.connect_timeout_seconds,self.read_timeout_seconds,self.total_timeout_seconds,self.max_request_bytes,self.max_response_bytes,self.max_concurrency)<=0 or self.read_timeout_seconds>self.total_timeout_seconds: raise ValueError("Invalid intelligence provider policy.")
        parsed=urlsplit(self.base_url)
        if parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"","/"}: raise ValueError("Invalid intelligence provider policy.")
        if parsed.port is not None and not 1<=parsed.port<=65535: raise ValueError("Invalid intelligence provider policy.")
        host=parsed.hostname.lower()
        if host in {"localhost","ollama"}: return
        try:
            address=ipaddress.ip_address(host)
            if not address.is_private and not address.is_loopback: raise ValueError("Invalid intelligence provider policy.")
            if address.is_link_local or address.is_multicast or address.is_unspecified: raise ValueError("Invalid intelligence provider policy.")
        except ValueError:
            raise ValueError("Invalid intelligence provider policy.") from None

@dataclass(frozen=True)
class TrustedPromptRequest:
    prompt_body:str; prompt_version:str=PROMPT_VERSION; candidate_schema_version:str=CANDIDATE_SCHEMA_VERSION; protocol_version:str=PROTOCOL_VERSION; idempotency_key:str=""
    def __post_init__(self):
        if self.prompt_version!=PROMPT_VERSION or self.candidate_schema_version!=CANDIDATE_SCHEMA_VERSION or self.protocol_version!=PROTOCOL_VERSION or not self.idempotency_key or len(self.idempotency_key)>128: raise ValueError("Invalid trusted prompt request.")
@dataclass(frozen=True)
class BoundedCandidateResponse: document:str; content_type:str="application/json"
class IntelligenceCandidateProvider(Protocol):
    def generate(self, request:TrustedPromptRequest, checkpoint:Callable[[],bool])->BoundedCandidateResponse: ...

class OllamaCandidateProvider:
    def __init__(self, policy:ProviderPolicy, *, client_factory=httpx.Client, semaphore:BoundedSemaphore|None=None): self.policy,self.client_factory,self.semaphore=policy,client_factory,semaphore or BoundedSemaphore(policy.max_concurrency)
    def generate(self, request, checkpoint):
        if len(request.prompt_body.encode())>self.policy.max_request_bytes: raise ProviderFailure(ProviderCategory.PROTOCOL_ERROR)
        if not checkpoint(): raise ProviderFailure(ProviderCategory.CANCELLED)
        if not self.semaphore.acquire(blocking=False): raise ProviderFailure(ProviderCategory.CONCURRENCY_LIMIT)
        try:
            timeout=httpx.Timeout(self.policy.total_timeout_seconds,connect=self.policy.connect_timeout_seconds,read=self.policy.read_timeout_seconds)
            try:
                with self.client_factory(timeout=timeout,follow_redirects=False) as client:
                    with client.stream("POST",self.policy.base_url+"/api/chat",json={"model":self.policy.model,"messages":[{"role":"user","content":request.prompt_body}],"format":"json","stream":False,"options":{"temperature":0}},headers={"Idempotency-Key":request.idempotency_key}) as response:
                        if response.status_code!=200: raise ProviderFailure(ProviderCategory.UNAVAILABLE if response.status_code>=500 else ProviderCategory.MODEL_UNAVAILABLE)
                        chunks=[]; size=0
                        for chunk in response.iter_bytes():
                            if not checkpoint(): raise ProviderFailure(ProviderCategory.CANCELLED)
                            size+=len(chunk)
                            if size>self.policy.max_response_bytes: raise ProviderFailure(ProviderCategory.RESPONSE_TOO_LARGE)
                            chunks.append(chunk)
            except ProviderFailure: raise
            except httpx.TimeoutException: raise ProviderFailure(ProviderCategory.TIMEOUT) from None
            except httpx.HTTPError: raise ProviderFailure(ProviderCategory.UNAVAILABLE) from None
            try: document=json.loads(b"".join(chunks)).get("message",{}).get("content")
            except (UnicodeDecodeError,json.JSONDecodeError): raise ProviderFailure(ProviderCategory.PROTOCOL_ERROR) from None
            if not isinstance(document,str) or not checkpoint(): raise ProviderFailure(ProviderCategory.PROTOCOL_ERROR if not isinstance(document,str) else ProviderCategory.CANCELLED)
            if len(document.encode())>self.policy.max_response_bytes: raise ProviderFailure(ProviderCategory.RESPONSE_TOO_LARGE)
            return BoundedCandidateResponse(document)
        except ProviderFailure: raise
        except Exception: raise ProviderFailure(ProviderCategory.INTERNAL) from None
        finally: self.semaphore.release()

class OllamaReadiness:
    def __init__(self, enabled:bool, policy:ProviderPolicy|None=None, *, client_factory=httpx.Client): self.enabled,self.policy,self.client_factory=enabled,policy,client_factory
    def check(self):
        if not self.enabled: return {"state":ReadinessState.DISABLED,"category":ProviderCategory.DISABLED}
        if self.policy is None: return {"state":ReadinessState.MISCONFIGURED,"category":ProviderCategory.MISCONFIGURED}
        try:
            with self.client_factory(timeout=httpx.Timeout(5.0),follow_redirects=False) as client: response=client.get(self.policy.base_url+"/api/tags")
            if response.status_code!=200: return {"state":ReadinessState.UNAVAILABLE,"category":ProviderCategory.UNAVAILABLE}
            names={entry.get("name") for entry in response.json().get("models",[]) if isinstance(entry,dict)}
            return {"state":ReadinessState.READY,"category":None} if self.policy.model in names else {"state":ReadinessState.UNAVAILABLE,"category":ProviderCategory.MODEL_UNAVAILABLE}
        except Exception: return {"state":ReadinessState.UNAVAILABLE,"category":ProviderCategory.UNAVAILABLE}
