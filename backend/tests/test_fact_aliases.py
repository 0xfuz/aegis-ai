"""Phase 5.5 canonical FACT alias contract tests."""
import json
from uuid import uuid4

import pytest

from app.modules.ai_reasoning.domain import intelligence_service
from app.modules.ai_reasoning.domain.intelligence_service import (
    alias_context,
    build_alias_map,
    resolve_aliases,
)
from app.shared.exceptions import ValidationError


def fact_context():
    ids = {name: str(uuid4()) for name in ("evidence", "raw", "event", "indicator", "entity", "relationship")}
    return ids, {
        "investigation_id": str(uuid4()),
        "evidence": [{"id": ids["evidence"], "name": "auth.log"}],
        "raw_records": [{"id": ids["raw"], "evidence_id": ids["evidence"], "ordinal": 1}],
        "events": [{"id": ids["event"], "source_record_id": ids["raw"], "type": "authentication"}],
        "indicators": [{"id": ids["indicator"], "value": "198.51.100.44"}],
        "entities": [{"id": ids["entity"], "value": "backup"}],
        "relationships": [{"id": ids["relationship"], "source_entity_id": ids["entity"], "event_id": ids["event"]}],
    }


def test_alias_generation_has_all_stable_fact_type_prefixes_and_is_deterministic():
    ids, context = fact_context()
    aliases = build_alias_map(context)
    assert aliases == build_alias_map(context)
    assert aliases == {"E1": ids["evidence"], "RR1": ids["raw"], "EV1": ids["event"], "IN1": ids["indicator"], "EN1": ids["entity"], "REL1": ids["relationship"]}


def test_alias_context_exposes_no_canonical_uuid_and_rewrites_references():
    ids, context = fact_context()
    projected = alias_context(context, build_alias_map(context))
    rendered = json.dumps(projected)
    assert "investigation_id" not in projected
    assert all(value not in rendered for value in ids.values())
    assert projected["events"][0]["id"] == "EV1"
    assert projected["relationships"][0]["source_entity_id"] == "EN1"


def test_aliases_resolve_only_against_the_current_analysis_map():
    ids, context = fact_context()
    aliases = build_alias_map(context)
    assert str(resolve_aliases(["EV1", "EN1"], aliases)[0]) == ids["event"]

    _other_ids, other_context = fact_context()
    other_context["events"] = []
    with pytest.raises(ValidationError, match="Unknown factual alias"):
        resolve_aliases(["EV1"], build_alias_map(other_context))


@pytest.mark.parametrize("alias", ["uuid-123", "EN0", "EN-1", str(uuid4())])
def test_invalid_or_unknown_aliases_are_rejected(alias):
    _ids, context = fact_context()
    with pytest.raises(ValidationError):
        resolve_aliases([alias], build_alias_map(context))


def test_duplicate_alias_prevention_is_enforced(monkeypatch):
    _ids, context = fact_context()
    monkeypatch.setitem(intelligence_service.ALIAS_PREFIXES, "events", "E")
    with pytest.raises(ValidationError, match="Duplicate factual alias"):
        build_alias_map(context)
