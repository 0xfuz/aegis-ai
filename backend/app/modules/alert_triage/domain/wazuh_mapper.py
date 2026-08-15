"""Pure Phase 7.8.1 Wazuh JSON to CanonicalAlertCreate mapping.

This module has no database, HTTP, connector, or downstream-service dependency.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError

from app.modules.alert_triage.domain.service import AlertObservables, CanonicalAlertCreate


class WazuhMappingError(ValueError):
    """The external alert cannot meet the approved canonical mapping contract."""


class _WazuhObject(BaseModel):
    model_config = ConfigDict(extra="allow")


class WazuhRule(_WazuhObject):
    id: str | int | None = None
    level: int | None = None
    description: str | None = None
    groups: list[str] = Field(default_factory=list)
    mitre: dict[str, Any] | None = None


class WazuhAlert(_WazuhObject):
    id: str | int | None = None
    timestamp: str | None = None
    rule: WazuhRule
    agent: _WazuhObject | None = None
    manager: _WazuhObject
    decoder: _WazuhObject | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    syscheck: dict[str, Any] = Field(default_factory=dict)
    location: str | None = None


_CATEGORY_GROUPS = (
    ("authentication_failures", "authentication_failed"),
    ("authentication_success", "authentication_success"),
    ("process", "process_execution"),
    ("syscheck", "file_integrity"),
    ("network", "network"),
    ("ids", "network"),
)
_NETWORK_DECODERS = {"json", "suricata", "zeek", "network"}
_RULE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def map_wazuh_alert(payload: dict[str, Any]) -> CanonicalAlertCreate:
    """Validate and project one Wazuh alert without performing any writes."""
    try:
        alert = WazuhAlert.model_validate(payload)
    except PydanticValidationError as exc:
        raise WazuhMappingError("Malformed Wazuh alert structure.") from exc

    manager_name = _text(_get(alert.manager, "name"), 255)
    alert_id = _text(alert.id, 255)
    if not manager_name or not alert_id:
        raise WazuhMappingError("Wazuh manager.name and alert id are required.")
    source_alert_id = f"wazuh:{manager_name.casefold().rstrip('.') }:{alert_id}"
    if len(source_alert_id) > 255:
        raise WazuhMappingError("Wazuh source identity exceeds the canonical limit.")
    if alert.rule.level is None or not isinstance(alert.rule.level, int) or not 0 <= alert.rule.level <= 16:
        raise WazuhMappingError("Wazuh rule.level must be an integer from 0 through 16.")

    # Wazuh's supported rule.id is the authoritative detector identity.  It
    # belongs in CanonicalAlert.rule_id, not an unbounded metadata blob.
    rule_id = _wazuh_rule_id(alert.rule.id)
    if rule_id is None:
        raise WazuhMappingError("Wazuh rule.id is required and must be a bounded identifier.")
    description = _text(alert.rule.description, 10_000) or ""
    title = _text(alert.rule.description, 255) or f"Wazuh rule {rule_id}"
    profile = (_text(_get(alert.decoder, "name"), 100) or "unknown").casefold()
    groups = tuple(sorted({_text(item, 100) for item in alert.rule.groups if _text(item, 100)}))
    diagnostics: list[str] = []

    hostname = _text(_get(alert.agent, "name"), 255)
    agent_id = _text(_get(alert.agent, "id"), 255)
    if not hostname and agent_id:
        hostname = f"agent-{agent_id}"
    fields = _profile_fields(profile, alert)
    observables = _safe_observables(hostname=hostname, diagnostics=diagnostics, **fields)
    metadata = _metadata(alert, manager_name, agent_id, profile, groups, diagnostics)
    try:
        return CanonicalAlertCreate(
            source="wazuh", source_alert_id=source_alert_id, observed_at=alert.timestamp,
            title=title, description=description, severity=_severity(alert.rule.level), category=_category(groups),
            rule_id=rule_id, rule_name=title, signature=f"wazuh:{rule_id}",
            observables=observables, source_metadata=metadata, normalizer_version="wazuh-alert-v1",
        )
    except PydanticValidationError as exc:
        raise WazuhMappingError("Wazuh alert violates the canonical alert contract.") from exc


def _profile_fields(profile: str, alert: WazuhAlert) -> dict[str, str | None]:
    data = alert.data
    if profile == "windows_eventchannel":
        event = _nested(data, "win", "eventdata")
        return {"username": _first(event, "targetUserName", "subjectUserName", "user", "userName"),
                "process": _first(event, "image", "processName", "commandLine"),
                "source_ip": _first(event, "ipAddress", "IpAddress"), "destination_ip": _first(event, "destinationIp"),
                "file": _first(event, "targetFilename", "fileName"), "domain": _first(event, "domain"), "url": _first(event, "url")}
    if profile in {"syslog", "linux", "ossec"}:
        return {"username": _first(data, "user", "srcuser", "dstuser"), "process": _first(data, "process", "program_name", "command"),
                "source_ip": _first(data, "srcip", "src_ip"), "destination_ip": _first(data, "dstip", "dest_ip"),
                "file": _first(data, "file", "path"), "domain": _first(data, "domain"), "url": _first(data, "url")}
    if profile == "syscheck":
        return {"username": _first(data, "user"), "process": _first(data, "process"), "source_ip": None, "destination_ip": None,
                "file": _first(alert.syscheck, "path"), "domain": None, "url": None}
    if profile in _NETWORK_DECODERS:
        return {"username": _first(data, "user", "srcuser"), "process": _first(data, "process", "program_name"),
                "source_ip": _first(data, "srcip", "src_ip"), "destination_ip": _first(data, "dstip", "dest_ip"),
                "file": _first(data, "file", "path"), "domain": _first(data, "domain", "hostname"), "url": _first(data, "url")}
    return {"username": None, "process": None, "source_ip": None, "destination_ip": None, "file": None, "domain": None, "url": None}


def _safe_observables(*, diagnostics: list[str], **values: str | None) -> AlertObservables:
    accepted: dict[str, str] = {}
    for key, value in values.items():
        text = _text(value, {"process": 1024, "file": 1024, "url": 2048, "domain": 253}.get(key, 255))
        if text is None:
            continue
        try:
            AlertObservables(**{key: text})
        except PydanticValidationError:
            diagnostics.append(f"omitted_invalid_{key}")
        else:
            accepted[key] = text
    return AlertObservables(**accepted)


def _metadata(alert: WazuhAlert, manager: str, agent_id: str | None, profile: str, groups: tuple[str, ...], diagnostics: list[str]) -> dict:
    network = {key: _valid_port(_first(alert.data, key)) for key in ("src_port", "srcport", "dest_port", "dstport")}
    network = {key: value for key, value in network.items() if value is not None}
    hashes = {key: _text(_first(alert.syscheck, key), 255) for key in ("md5", "sha1", "sha256")}
    wazuh: dict[str, Any] = {"manager_name": manager, "agent_id": agent_id, "agent_ip": _text(_get(alert.agent, "ip"), 45),
        "decoder": profile, "location": _text(alert.location, 255), "rule_groups": list(groups), "mitre": _mitre(alert.rule.mitre)}
    wazuh = {key: value for key, value in wazuh.items() if value not in (None, [], {})}
    if network: wazuh["network"] = network
    if any(hashes.values()): wazuh["hashes"] = {key: value for key, value in hashes.items() if value}
    if diagnostics: wazuh["mapping_diagnostics"] = sorted(set(diagnostics))
    return {"wazuh": wazuh}


def _mitre(value: dict[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(value, dict): return {}
    return {key: sorted({_text(item, 100) for item in raw if _text(item, 100)}) for key in ("id", "tactic", "technique") if isinstance((raw := value.get(key)), list)}


def _severity(level: int) -> str:
    return "INFO" if level <= 3 else "LOW" if level <= 6 else "MEDIUM" if level <= 9 else "HIGH" if level <= 12 else "CRITICAL"


def _category(groups: tuple[str, ...]) -> str:
    lowered = {item.casefold() for item in groups}
    return next((category for group, category in _CATEGORY_GROUPS if group in lowered), "wazuh_unclassified")


def _text(value: Any, maximum: int) -> str | None:
    if not isinstance(value, (str, int)): return None
    text = str(value).strip()
    return text if text and len(text) <= maximum else None


def _wazuh_rule_id(value: Any) -> str | None:
    text = _text(value, 128)
    return text if text and _RULE_ID.fullmatch(text) else None


def _get(value: _WazuhObject | None, key: str) -> Any:
    return getattr(value, key, None) if value else None


def _nested(value: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = value.get(key, {}) if isinstance(value, dict) else {}
    return value if isinstance(value, dict) else {}


def _first(value: dict[str, Any], *keys: str) -> Any:
    return next((value[key] for key in keys if value.get(key) not in (None, "")), None)


def _valid_port(value: Any) -> int | None:
    try: port = int(value)
    except (TypeError, ValueError): return None
    return port if 1 <= port <= 65535 else None
