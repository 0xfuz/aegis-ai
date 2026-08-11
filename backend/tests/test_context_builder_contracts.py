import json
from app.modules.ai_reasoning.domain.context_builder import ContextPolicy, sanitize


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
