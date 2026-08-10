"""Bounded, deterministic parsers for Phase 2 supported file types."""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from typing import Any

from app.modules.evidence.domain.types import (
    EntityCandidate,
    EvidenceParser,
    NormalizedEvent,
    ParsedRecord,
    RelationshipCandidate,
)
from app.shared.exceptions import ValidationError

_SSH = re.compile(
    r"^\S+\s+\d+\s+\S+\s+(?P<host>\S+)\s+sshd\[\d+\]:\s+"
    r"(?P<action>Accepted|Failed)\s+password\s+for\s+(?:invalid\s+user\s+)?"
    r"(?P<user>\S+)\s+from\s+(?P<source_ip>\S+)",
    re.IGNORECASE,
)
_PROCESS = re.compile(r"^\S+\s+\d+\s+\S+\s+(?P<host>\S+)\s+(?P<process>[\w.-]+)\[\d+\]:\s+(?P<action>.+)$")


def _to_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _to_port(value: Any) -> int | None:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    return port if 0 <= port <= 65535 else None


def _value(row: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _derive(event: NormalizedEvent, extra_entities: tuple[EntityCandidate, ...] = ()) -> tuple[tuple[EntityCandidate, ...], tuple[RelationshipCandidate, ...]]:
    entities: list[EntityCandidate] = list(extra_entities)
    relationships: list[RelationshipCandidate] = []
    host = EntityCandidate("host", event.host) if event.host else None
    user = EntityCandidate("user", event.user) if event.user else None
    source_ip = EntityCandidate("ip", event.source_ip) if event.source_ip else None
    destination_ip = EntityCandidate("ip", event.destination_ip) if event.destination_ip else None
    process = EntityCandidate("process", event.process) if event.process else None
    for candidate in (host, user, source_ip, destination_ip, process):
        if candidate and candidate not in entities:
            entities.append(candidate)
    if user and host:
        relationships.append(RelationshipCandidate(user, host, "logged_into"))
    if process and host:
        relationships.append(RelationshipCandidate(process, host, "executed_on"))
    if host and destination_ip:
        relationships.append(RelationshipCandidate(host, destination_ip, "connected_to"))
    domain = next((e for e in extra_entities if e.type == "domain"), None)
    if domain and destination_ip:
        relationships.append(RelationshipCandidate(domain, destination_ip, "resolved_to"))
    return tuple(entities), tuple(relationships)


def _event_from_row(row: dict[str, Any], source_default: str) -> NormalizedEvent:
    source_ip = _value(row, "source_ip", "src_ip", "sourceIp")
    destination_ip = _value(row, "destination_ip", "dest_ip", "destinationIp", "resolved_ip")
    return NormalizedEvent(
        timestamp=_to_datetime(_value(row, "timestamp", "time", "event_time")),
        source=_value(row, "source") or source_default,
        host=_value(row, "host", "hostname"),
        user=_value(row, "user", "username"),
        process=_value(row, "process", "process_name"),
        source_ip=source_ip,
        destination_ip=destination_ip,
        source_port=_to_port(_value(row, "source_port", "src_port", "sourcePort")),
        destination_port=_to_port(_value(row, "destination_port", "dest_port", "destinationPort")),
        event_type=_value(row, "event_type", "type") or source_default,
        action=_value(row, "action", "message", "query"),
        deterministic_severity=_value(row, "severity"),
        normalized=dict(row),
    )


class PlainTextParser:
    parser_id = "plain-text"
    parser_version = "1.0.0"
    supported_extensions = (".log", ".txt")

    def supports(self, filename: str, detected_mime: str) -> bool:
        return filename.lower().endswith(self.supported_extensions)

    def parse(self, content: str) -> list[ParsedRecord]:
        records: list[ParsedRecord] = []
        offset = 0
        for line_number, line in enumerate(content.splitlines(keepends=True), start=1):
            text = line.rstrip("\r\n")
            current_offset = offset
            offset += len(line.encode("utf-8"))
            if not text:
                continue
            ssh = _SSH.match(text)
            process = _PROCESS.match(text)
            if ssh:
                event = NormalizedEvent(
                    source="plain-text", host=ssh.group("host"), user=ssh.group("user"),
                    source_ip=ssh.group("source_ip"), event_type="authentication",
                    action=ssh.group("action").lower(), normalized={"message": text},
                )
            elif process:
                event = NormalizedEvent(
                    source="plain-text", host=process.group("host"), process=process.group("process"),
                    event_type="process", action=process.group("action"), normalized={"message": text},
                )
            else:
                event = NormalizedEvent(source="plain-text", event_type="raw", normalized={"message": text})
            entities, relationships = _derive(event)
            records.append(ParsedRecord(text, "text/plain", current_offset, line_number, line_number, event, entities, relationships))
        return records


class JsonParser:
    parser_id = "json"
    parser_version = "1.0.0"
    supported_extensions = (".json",)

    def supports(self, filename: str, detected_mime: str) -> bool:
        return filename.lower().endswith(".json")

    def parse(self, content: str) -> list[ParsedRecord]:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValidationError("Malformed JSON evidence.") from exc
        rows = payload if isinstance(payload, list) else [payload]
        if not all(isinstance(row, dict) for row in rows):
            raise ValidationError("JSON evidence must be an object or an array of objects.")
        records: list[ParsedRecord] = []
        for ordinal, row in enumerate(rows, start=1):
            row = dict(row)
            event = _event_from_row(row, "json")
            query = _value(row, "query", "domain")
            extras = (EntityCandidate("domain", query),) if query else ()
            entities, relationships = _derive(event, extras)
            records.append(ParsedRecord(json.dumps(row, sort_keys=True, separators=(",", ":")), "application/json", None, ordinal, ordinal, event, entities, relationships))
        return records


class AlertPromotionJsonParser:
    """Parses only the deterministic Phase 7.5 alert-promotion export."""

    parser_id = "alert-promotion-json"
    parser_version = "1.0.0"

    def supports(self, filename: str, detected_mime: str) -> bool:
        return filename.lower() == "alert-promotion-v1.json"

    def parse(self, content: str) -> list[ParsedRecord]:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValidationError("Malformed JSON evidence.") from exc
        if not isinstance(payload, dict) or payload.get("format") != "aegis.alert-promotion.export" or payload.get("version") != "1.0":
            raise ValidationError("Invalid alert-promotion export format.")
        alerts = payload.get("alerts")
        if not isinstance(alerts, list) or not alerts or not all(isinstance(alert, dict) for alert in alerts):
            raise ValidationError("Alert-promotion export must contain one or more alert objects.")
        records: list[ParsedRecord] = []
        for ordinal, alert in enumerate(alerts, start=1):
            observables = alert.get("observables")
            if not isinstance(observables, dict) or not isinstance(alert.get("observed_at"), str):
                raise ValidationError("Alert-promotion alert has invalid canonical fields.")
            timestamp = _to_datetime(alert["observed_at"])
            if timestamp is None:
                raise ValidationError("Alert-promotion observed_at must include a timezone.")
            source = alert.get("source")
            severity = alert.get("severity")
            if not isinstance(source, str) or not source or severity not in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}:
                raise ValidationError("Alert-promotion alert has invalid source or severity.")
            event = NormalizedEvent(
                timestamp=timestamp, source=f"alert-promotion:{source}", host=_value(observables, "hostname", "host"),
                user=_value(observables, "username", "user"), process=_value(observables, "process"),
                source_ip=_value(observables, "source_ip"), destination_ip=_value(observables, "destination_ip"),
                event_type=alert.get("category") if isinstance(alert.get("category"), str) else "alert_promotion",
                action=_value(alert, "rule_id", "rule_name", "signature"), deterministic_severity=severity.lower(), normalized=dict(alert),
            )
            domain = _value(observables, "domain")
            extras = (EntityCandidate("domain", domain),) if domain else ()
            entities, relationships = _derive(event, extras)
            records.append(ParsedRecord(json.dumps(alert, sort_keys=True, separators=(",", ":")), "application/json", None, ordinal, ordinal, event, entities, relationships))
        return records


class CsvParser:
    parser_id = "csv"
    parser_version = "1.0.0"
    supported_extensions = (".csv",)

    def supports(self, filename: str, detected_mime: str) -> bool:
        return filename.lower().endswith(".csv")

    def parse(self, content: str) -> list[ParsedRecord]:
        try:
            reader = csv.DictReader(io.StringIO(content, newline=""))
            if not reader.fieldnames or any(not name for name in reader.fieldnames):
                raise ValidationError("CSV evidence must include non-empty headers.")
            rows = list(reader)
        except csv.Error as exc:
            raise ValidationError("Malformed CSV evidence.") from exc
        records: list[ParsedRecord] = []
        for ordinal, row in enumerate(rows, start=2):
            if None in row:
                raise ValidationError("CSV row contains more fields than its header.")
            normalized_row = {str(key): (value or "") for key, value in row.items()}
            event = _event_from_row(normalized_row, "csv")
            entities, relationships = _derive(event)
            records.append(ParsedRecord(json.dumps(normalized_row, sort_keys=True, separators=(",", ":")), "text/csv", None, ordinal, ordinal, event, entities, relationships))
        return records


class ParserRegistry:
    def __init__(self, parsers: tuple[EvidenceParser, ...] | None = None):
        self._parsers = parsers or (PlainTextParser(), AlertPromotionJsonParser(), JsonParser(), CsvParser())

    def select(self, filename: str, detected_mime: str) -> EvidenceParser:
        for parser in self._parsers:
            if parser.supports(filename, detected_mime):
                return parser
        raise ValidationError("Unsupported evidence format. Only .log, .txt, .json, and .csv are accepted.")
