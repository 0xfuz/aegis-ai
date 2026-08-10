"""Phase 7.8.1 pure Wazuh mapping contract tests; no ingress or writes."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.alert_triage.domain.wazuh_mapper import WazuhMappingError, map_wazuh_alert
from app.modules.alert_triage.infrastructure.models import CanonicalAlert
from app.modules.evidence.infrastructure.models import Entity, EntityRelationship, Event, EvidenceItem, Indicator, RawRecord
from app.modules.identity.infrastructure.models import Organization
from app.modules.investigations.infrastructure.models import Finding, MitreMapping
from app.shared.database import SessionLocal


FIXTURES = Path(__file__).parent / "fixtures" / "wazuh"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.parametrize("name", [
    "windows_authentication.json", "linux_process.json", "network_event.json", "file_integrity.json",
    "mitre_metadata.json", "sparse_valid.json",
])
def test_approved_sanitized_fixtures_map_deterministically(name):
    payload = fixture(name)
    assert map_wazuh_alert(payload).model_dump(mode="json") == map_wazuh_alert(deepcopy(payload)).model_dump(mode="json")


def test_windows_mapping_and_source_asserted_mitre_metadata():
    mapped = map_wazuh_alert(fixture("windows_authentication.json"))
    assert mapped.source_alert_id == "wazuh:wazuh-lab:1710000000.1001"
    assert mapped.severity == "HIGH" and mapped.category == "authentication_failed"
    assert mapped.observables.stored() == {"source_ip": "198.51.100.41", "hostname": "win-lab-01", "username": "lab-user", "process": "c:\\windows\\system32\\lsass.exe"}
    assert mapped.source_metadata["wazuh"]["mitre"] == {"id": ["T1110"], "tactic": ["Credential Access"], "technique": ["Brute Force"]}
    assert "mitre_mappings" not in mapped.source_metadata and "organization_id" not in mapped.model_dump()


def test_linux_network_and_file_integrity_profiles_map_only_approved_fields():
    linux = map_wazuh_alert(fixture("linux_process.json"))
    network = map_wazuh_alert(fixture("network_event.json"))
    fim = map_wazuh_alert(fixture("file_integrity.json"))
    assert linux.observables.stored()["process"] == "/usr/sbin/sshd" and linux.category == "authentication_failed"
    assert network.observables.stored() == {"source_ip": "198.51.100.30", "destination_ip": "203.0.113.53", "hostname": "sensor-lab-01", "domain": "example.test", "url": "https://example.test/health"}
    assert network.source_metadata["wazuh"]["network"] == {"src_port": 51515, "dest_port": 443}
    assert fim.observables.stored()["file"] == "/var/tmp/aegis-lab.txt"
    assert fim.source_metadata["wazuh"]["hashes"]["sha256"].startswith("012345")


def test_sparse_valid_alert_and_agent_id_hostname_fallback_work():
    sparse = map_wazuh_alert(fixture("sparse_valid.json"))
    assert sparse.title == "Minimal Wazuh alert" and sparse.observables.stored() == {}
    payload = fixture("sparse_valid.json"); payload["agent"] = {"id": "007"}
    assert map_wazuh_alert(payload).observables.stored()["hostname"] == "agent-007"


def test_missing_id_and_malformed_timestamp_are_rejected():
    no_id = fixture("sparse_valid.json"); no_id.pop("id")
    malformed_time = fixture("sparse_valid.json"); malformed_time["timestamp"] = "not-a-timestamp"
    with pytest.raises(WazuhMappingError, match="alert id"):
        map_wazuh_alert(no_id)
    with pytest.raises(WazuhMappingError, match="canonical"):
        map_wazuh_alert(malformed_time)


def test_invalid_optional_ip_is_safely_omitted_with_diagnostic():
    payload = fixture("network_event.json"); payload["data"]["src_ip"] = "not-an-ip"
    mapped = map_wazuh_alert(payload)
    assert "source_ip" not in mapped.observables.stored()
    assert mapped.source_metadata["wazuh"]["mapping_diagnostics"] == ["omitted_invalid_source_ip"]


def test_hostile_text_is_inert_data_and_payload_cannot_supply_aegis_tenant_identity():
    payload = fixture("sparse_valid.json")
    payload["organization_id"] = "attacker-chosen"
    payload["rule"]["description"] = "<script>alert(1)</script>; $(do-not-run)"
    mapped = map_wazuh_alert(payload)
    assert mapped.title == "<script>alert(1)</script>; $(do-not-run)"
    dumped = mapped.model_dump(mode="json")
    assert "organization_id" not in dumped and "attacker-chosen" not in json.dumps(dumped)


def test_pure_mapping_performs_no_database_or_fact_mitre_finding_writes():
    db = SessionLocal()
    try:
        models = [Organization, CanonicalAlert, EvidenceItem, RawRecord, Event, Indicator, Entity, EntityRelationship, IntelligenceAnalysis, Finding, MitreMapping]
        before = {model.__name__: db.scalar(select(func.count()).select_from(model)) for model in models}
        map_wazuh_alert(fixture("mitre_metadata.json"))
        after = {model.__name__: db.scalar(select(func.count()).select_from(model)) for model in models}
        assert before == after
    finally:
        db.rollback(); db.close()
