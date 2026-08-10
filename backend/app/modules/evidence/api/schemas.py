from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    investigation_id: UUID
    original_filename: str
    sha256: str
    byte_size: int
    detected_mime: str
    extension: str
    source_description: str
    acquisition_source: str
    imported_at: datetime
    parsing_status: str
    # Additive, safe read-model metadata from the latest parse run.
    parser_name: str | None = None
    parser_version: str | None = None


class EvidenceDetail(EvidenceRead):
    pass


class RawRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    ordinal: int
    content: str | None
    content_type: str
    byte_offset: int | None
    line_start: int | None
    line_end: int | None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    evidence_id: UUID
    raw_record_id: UUID
    timestamp: datetime | None
    source: str | None
    host: str | None
    user: str | None
    process: str | None
    source_ip: str | None
    destination_ip: str | None
    source_port: int | None
    destination_port: int | None
    event_type: str | None
    action: str | None
    deterministic_severity: str | None
    normalized: dict


class IndicatorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    type: str
    normalized_value: str
    display_value: str | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    occurrence_count: int


class EntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    type: str
    canonical_value: str
    display_name: str
    attributes: dict | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None


class EntityRelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relationship_type: str
    evidence_id: UUID | None
    raw_record_id: UUID | None
    event_id: UUID | None
    observed_at: datetime | None


class IndicatorOccurrenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    evidence_id: UUID
    raw_record_id: UUID
    event_id: UUID | None
    observed_at: datetime | None


class EntityObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    evidence_id: UUID
    raw_record_id: UUID
    event_id: UUID | None
    observed_at: datetime | None
