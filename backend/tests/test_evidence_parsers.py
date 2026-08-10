from pathlib import Path

import pytest

from app.modules.evidence.domain.parsers import ParserRegistry
from app.shared.exceptions import ValidationError

FIXTURES = Path(__file__).parent / "fixtures" / "evidence"


def test_supported_parsers_are_deterministic():
    registry = ParserRegistry()
    for filename in ("auth.log", "dns.json", "connections.csv"):
        content = (FIXTURES / filename).read_text()
        parser = registry.select(filename, "")
        assert parser.parse(content) == parser.parse(content)


def test_text_json_and_csv_normalize_only_present_fields():
    registry = ParserRegistry()
    text = registry.select("auth.log", "").parse((FIXTURES / "auth.log").read_text())
    assert text[0].event.user == "guest"
    assert text[0].event.timestamp is None  # syslog year is not fabricated
    assert text[0].relationships[0].relationship_type == "logged_into"

    json_records = registry.select("dns.json", "").parse((FIXTURES / "dns.json").read_text())
    assert json_records[0].event.destination_ip == "203.0.113.9"
    assert any(link.relationship_type == "resolved_to" for link in json_records[0].relationships)

    csv_records = registry.select("connections.csv", "").parse((FIXTURES / "connections.csv").read_text())
    assert csv_records[0].event.destination_port == 443
    assert any(link.relationship_type == "executed_on" for link in csv_records[0].relationships)


def test_malformed_json_and_csv_are_rejected():
    registry = ParserRegistry()
    with pytest.raises(ValidationError):
        registry.select("bad.json", "").parse((FIXTURES / "malformed.json").read_text())
    with pytest.raises(ValidationError):
        registry.select("bad.csv", "").parse("a,b\n1,2,3\n")
