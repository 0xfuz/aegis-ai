"""Pure parser contracts; no database, filesystem, or AI dependencies."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class EntityCandidate:
    type: str
    value: str
    display_name: str | None = None


@dataclass(frozen=True)
class RelationshipCandidate:
    source: EntityCandidate
    target: EntityCandidate
    relationship_type: str


@dataclass(frozen=True)
class NormalizedEvent:
    timestamp: datetime | None = None
    source: str | None = None
    host: str | None = None
    user: str | None = None
    process: str | None = None
    source_ip: str | None = None
    destination_ip: str | None = None
    source_port: int | None = None
    destination_port: int | None = None
    event_type: str | None = None
    action: str | None = None
    deterministic_severity: str | None = None
    normalized: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedRecord:
    content: str
    content_type: str
    byte_offset: int | None
    line_start: int | None
    line_end: int | None
    event: NormalizedEvent | None
    entities: tuple[EntityCandidate, ...] = ()
    relationships: tuple[RelationshipCandidate, ...] = ()


class EvidenceParser(Protocol):
    parser_id: str
    parser_version: str
    supported_extensions: tuple[str, ...]

    def supports(self, filename: str, detected_mime: str) -> bool: ...
    def parse(self, content: str) -> list[ParsedRecord]: ...
