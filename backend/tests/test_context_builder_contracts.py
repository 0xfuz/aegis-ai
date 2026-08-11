import json
import pytest
from app.modules.ai_reasoning.domain.context_builder import ContextPolicy, sanitize
from app.modules.ai_reasoning.domain.context_builder import ContextBuilder
from app.shared.exceptions import ValidationError


def test_sanitizer_redacts_credentials_without_destroying_iocs():
    warnings=[]
    value={"Authorization":"Bearer very-long-sensitive-token-value", "sha256":"a"*64, "ip":"198.51.100.9", "nested":{"api_key":"nope","command":"echo harmless"}}
    clean=sanitize(value,ContextPolicy(),warnings)
    encoded=json.dumps(clean)
    assert "very-long-sensitive" not in encoded and "nope" not in encoded
    assert "a"*64 in encoded and "198.51.100.9" in encoded and "echo harmless" in encoded
    assert any(row["code"]=="SENSITIVE_REDACTED" for row in warnings)


def test_sanitizer_has_deterministic_depth_and_collection_bounds():
    policy=ContextPolicy(max_depth=2,max_collection=2,max_text=5)
    left=[]; right=[]
    value={"z":["abcdef", "second", "third"], "a":{"deep":{"x":"hidden"}}, "m":"middle"}
    assert sanitize(value,policy,left)==sanitize(value,policy,right)
    assert left==right and any(row["code"]=="JSON_COLLECTION_TRUNCATED" for row in left)

def test_total_size_finalization_is_deterministic_and_removes_aliases():
    builder=ContextBuilder(None,ContextPolicy(max_bytes=900)); base={"aliases":{"FI1":{"id":"1"},"MT1":{"id":"2"}},"omissions":[],"section_counts":{"findings":1,"mitre":1,"relationships":0,"indicators":0,"entities":0,"raw_records":0,"evidence":0,"events":0,"alerts":0,"correlation_v2":0},"findings":[{"alias":"FI1","text":"x"*300}],"mitre":[{"alias":"MT1","text":"x"*300}],"relationships":[],"indicators":[],"entities":[],"raw_records":[],"evidence":[],"events":[],"alerts":[],"correlation_v2":[],"required":"safe"}
    builder._finalize_size(base)
    assert len(json.dumps(base,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode())<=900
    assert "MT1" not in base["aliases"] and any(x["reason"]=="TOTAL_SIZE" for x in base["omissions"])

def test_impossible_total_size_fails_safely():
    builder=ContextBuilder(None,ContextPolicy(max_bytes=1)); snapshot={"aliases":{},"omissions":[],"section_counts":{name:0 for name in ("findings","mitre","relationships","indicators","entities","raw_records","evidence","events","alerts","correlation_v2")},**{name:[] for name in ("findings","mitre","relationships","indicators","entities","raw_records","evidence","events","alerts","correlation_v2")},"required":"safe"}
    with pytest.raises(ValidationError,match="mandatory metadata"): builder._finalize_size(snapshot)
