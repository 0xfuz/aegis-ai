from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class EvidenceImporterRead(BaseModel):
    """Bounded display identity for an already-authorized evidence reader."""
    id: UUID
    display_name: str = Field(max_length=255)


class EvidenceInventoryItem(BaseModel):
    """Safe list projection.  It intentionally excludes source prose and raw data."""
    id: UUID
    filename: str = Field(max_length=1024)
    detected_mime: str = Field(max_length=255)
    byte_size: int
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acquisition_source: str = Field(max_length=100)
    imported_at: datetime
    parsing_status: str = Field(max_length=20)
    latest_parse_status: str | None = Field(default=None, max_length=20)
    parser_name: str | None = Field(default=None, max_length=100)
    parser_version: str | None = Field(default=None, max_length=100)
    parse_warning_count: int
    raw_record_count: int
    raw_content_unavailable_count: int
    event_count: int
    importer: EvidenceImporterRead | None = None


class EvidenceInventoryPage(BaseModel):
    items: list[EvidenceInventoryItem]
    limit: int
    offset: int
    total: int


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


class TimelineEvidenceRead(BaseModel):
    id: UUID
    filename: str = Field(max_length=1024)


class TimelineEventRead(BaseModel):
    """Bounded canonical Event projection; normalized JSON is never returned."""
    id: UUID
    timestamp: datetime | None
    time_basis: str = Field(max_length=32)
    event_type: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=255)
    host: str | None = Field(default=None, max_length=255)
    user: str | None = Field(default=None, max_length=255)
    source_ip: str | None = Field(default=None, max_length=64)
    destination_ip: str | None = Field(default=None, max_length=64)
    deterministic_severity: str | None = Field(default=None, max_length=20)
    evidence: TimelineEvidenceRead
    raw_content_available: bool
    raw_locator_available: bool
    provenance_status: str = Field(max_length=64)


class TimelinePage(BaseModel):
    items: list[TimelineEventRead]
    limit: int
    offset: int
    returned_count: int
    total: int


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


class EntityListItem(BaseModel):
    id: UUID
    type: str = Field(max_length=50)
    display_value: str = Field(max_length=2048)
    observation_count: int
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    provenance_available_count: int


class EntityObservationItem(BaseModel):
    id: UUID
    observed_at: datetime | None
    extractor_name: str = Field(max_length=100)
    extractor_version: str = Field(max_length=100)
    evidence_id: UUID
    raw_record_id: UUID
    event_id: UUID | None
    provenance_status: str = Field(max_length=64)


class IndicatorOccurrenceItem(BaseModel):
    id: UUID
    indicator_id: UUID
    type: str = Field(max_length=50)
    canonical_value: str = Field(max_length=2048)
    observed_at: datetime | None
    extractor_name: str = Field(max_length=100)
    extractor_version: str = Field(max_length=100)
    evidence_id: UUID
    raw_record_id: UUID
    event_id: UUID | None
    provenance_status: str = Field(max_length=64)


class EntityPage(BaseModel):
    items: list[EntityListItem]
    limit: int
    offset: int
    returned_count: int
    total: int


class EntityObservationPage(BaseModel):
    items: list[EntityObservationItem]
    limit: int
    offset: int
    returned_count: int
    total: int


class IndicatorOccurrencePage(BaseModel):
    items: list[IndicatorOccurrenceItem]
    limit: int
    offset: int
    returned_count: int
    total: int
