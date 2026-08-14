from threading import BoundedSemaphore
from types import SimpleNamespace
import httpx
import pytest
from app.modules.ai_reasoning.domain.trusted_provider import (BoundedCandidateResponse, OllamaCandidateProvider, OllamaReadiness, PROMPT_VERSION, ProviderCategory, ProviderFailure, ProviderPolicy, ReadinessState, TrustedPromptRequest)

def policy(**overrides):
    values=dict(provider="ollama",base_url="http://ollama:11434",model="llama3.2:latest",allowed_models=("llama3.2:latest",),connect_timeout_seconds=5,read_timeout_seconds=45,total_timeout_seconds=60,max_request_bytes=1024,max_response_bytes=1024,max_concurrency=1);values.update(overrides);return ProviderPolicy(**values)
def request(**overrides):
    values=dict(prompt_body='{"safe":true}',idempotency_key="run-key");values.update(overrides);return TrustedPromptRequest(**values)
def factory(handler): return lambda **kwargs: httpx.Client(transport=httpx.MockTransport(handler),**kwargs)

def test_policy_defaults_are_deterministic_and_disabled_by_default():
    settings=SimpleNamespace(INTELLIGENCE_PROVIDER="ollama",INTELLIGENCE_OLLAMA_BASE_URL="http://ollama:11434",INTELLIGENCE_OLLAMA_MODEL="llama3.2:latest",INTELLIGENCE_OLLAMA_ALLOWED_MODELS="llama3.2:latest",INTELLIGENCE_PROVIDER_CONNECT_TIMEOUT_SECONDS=5,INTELLIGENCE_PROVIDER_READ_TIMEOUT_SECONDS=45,INTELLIGENCE_PROVIDER_TOTAL_TIMEOUT_SECONDS=60,INTELLIGENCE_PROVIDER_MAX_REQUEST_BYTES=1024,INTELLIGENCE_PROVIDER_MAX_RESPONSE_BYTES=1024,INTELLIGENCE_PROVIDER_MAX_CONCURRENCY=2)
    assert ProviderPolicy.from_settings(settings).model=="llama3.2:latest" and PROMPT_VERSION=="intelligence-evidence-grounded-v1"
    assert OllamaReadiness(False,policy()).check()=={"state":ReadinessState.DISABLED,"category":ProviderCategory.DISABLED}

@pytest.mark.parametrize("url",["https://example.com","http://169.254.169.254","http://user:pass@ollama:11434","http://ollama:11434/?x=1","http://ollama:11434/#x","ftp://ollama:11434","http://[::]/"])
def test_policy_rejects_untrusted_provider_urls(url):
    with pytest.raises(ValueError): policy(base_url=url)
@pytest.mark.parametrize("kwargs",[{"provider":"gemini"},{"model":"other"},{"model":"llama3.2:latest","allowed_models":("llama3.2",)},{"model":"llama3.2:latest:bad"},{"model":"llama3.2 latest"},{"model":"https://model"},{"read_timeout_seconds":61},{"max_request_bytes":0},{"max_concurrency":0}])
def test_policy_rejects_unsafe_bounds_and_provider(kwargs):
    with pytest.raises(ValueError): policy(**kwargs)

def test_adapter_uses_only_trusted_model_json_mode_and_bounded_response():
    seen={}
    def handler(req):
        seen.update(json=req.json() if False else None, url=str(req.url), key=req.headers.get("idempotency-key"));return httpx.Response(200,json={"message":{"content":"{}"}})
    result=OllamaCandidateProvider(policy(),client_factory=factory(handler)).generate(request(),lambda:True)
    assert result==BoundedCandidateResponse("{}") and seen["url"].endswith("/api/chat") and seen["key"]=="run-key"

def test_adapter_rejects_cancellation_protocol_and_size_without_side_effects():
    adapter=OllamaCandidateProvider(policy(max_response_bytes=3),client_factory=factory(lambda _:httpx.Response(200,json={"message":{"content":"{}"}})))
    with pytest.raises(ProviderFailure,match="PROVIDER_CANCELLED"): adapter.generate(request(),lambda:False)
    with pytest.raises(ProviderFailure,match="PROVIDER_RESPONSE_TOO_LARGE"): adapter.generate(request(),lambda:True)
    malformed=OllamaCandidateProvider(policy(),client_factory=factory(lambda _:httpx.Response(200,json={"wrong":True})))
    with pytest.raises(ProviderFailure,match="PROVIDER_PROTOCOL_ERROR"): malformed.generate(request(),lambda:True)

def test_adapter_releases_concurrency_permit_after_failure_and_rejects_excess():
    semaphore=BoundedSemaphore(1);adapter=OllamaCandidateProvider(policy(),semaphore=semaphore,client_factory=factory(lambda _:httpx.Response(500)))
    with pytest.raises(ProviderFailure,match="PROVIDER_UNAVAILABLE"): adapter.generate(request(),lambda:True)
    assert semaphore.acquire(blocking=False);semaphore.release()
    semaphore.acquire()
    with pytest.raises(ProviderFailure,match="PROVIDER_CONCURRENCY_LIMIT"): adapter.generate(request(),lambda:True)
    semaphore.release()

def test_readiness_is_non_generating_and_returns_only_safe_state_category():
    ready=OllamaReadiness(True,policy(),client_factory=factory(lambda req:httpx.Response(200,json={"models":[{"name":"llama3.2:latest"}]}))).check()
    missing=OllamaReadiness(True,policy(),client_factory=factory(lambda req:httpx.Response(200,json={"models":[]}))).check()
    assert ready=={"state":ReadinessState.READY,"category":None}
    assert missing=={"state":ReadinessState.UNAVAILABLE,"category":ProviderCategory.MODEL_UNAVAILABLE}

def test_trusted_request_rejects_unapproved_versions_or_unbounded_key():
    with pytest.raises(ValueError): request(prompt_version="client")
    with pytest.raises(ValueError): request(idempotency_key="x"*129)
