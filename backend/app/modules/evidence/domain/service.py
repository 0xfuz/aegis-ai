"""Synchronous, deterministic, AI-free canonical evidence ingestion."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.evidence.domain.indicators import extract_indicators
from app.modules.evidence.domain.parsers import ParserRegistry
from app.modules.evidence.domain.types import EntityCandidate, ParsedRecord
from app.modules.evidence.infrastructure.models import (
    AuditEvent, Entity, EntityObservation, EntityRelationship, Event, EvidenceItem,
    EvidenceParseRun, Indicator, IndicatorOccurrence, RawRecord,
)
from app.modules.evidence.infrastructure.repository import EvidenceRepository
from app.modules.evidence.infrastructure.storage import EvidenceStorage
from app.modules.investigations.domain.service import InvestigationService
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError

_EXTENSIONS = {".log", ".txt", ".json", ".csv"}
_MIME_BY_EXTENSION = {
    ".log": {"", "text/plain", "application/octet-stream"},
    ".txt": {"", "text/plain", "application/octet-stream"},
    ".json": {"", "application/json", "text/json", "application/octet-stream"},
    ".csv": {"", "text/csv", "application/csv", "text/plain", "application/octet-stream"},
}


class EvidenceIngestionService:
    def __init__(self, db: Session, settings: Settings, registry: ParserRegistry | None = None):
        self.db = db
        self.settings = settings
        self.registry = registry or ParserRegistry()
        self.storage = EvidenceStorage(settings)
        self.repo = EvidenceRepository(db)

    def ingest(self, org_id: UUID, investigation_id: UUID, actor_id: UUID, upload, *, atomic: bool = False,
               acquisition_source: str = "manual_upload") -> EvidenceItem:
        investigation = InvestigationService(self.db).get_investigation(org_id, investigation_id)
        supplied_filename = upload.filename or ""
        if "/" in supplied_filename or "\\" in supplied_filename:
            self._audit(org_id, investigation_id, actor_id, "EVIDENCE_REJECTED", "Investigation", investigation_id, "Path-like filename")
            self._finish(atomic)
            raise ValidationError("Evidence filenames must not include path components.")
        filename = Path(supplied_filename).name
        extension = Path(filename).suffix.lower()
        if not filename or extension not in _EXTENSIONS:
            self._audit(org_id, investigation_id, actor_id, "EVIDENCE_REJECTED", "Investigation", investigation_id, "Unsupported extension")
            self._finish(atomic)
            raise ValidationError("Only .log, .txt, .json, and .csv evidence is supported.")
        declared_mime = (upload.content_type or "").lower()
        if declared_mime not in _MIME_BY_EXTENSION[extension]:
            self._audit(org_id, investigation_id, actor_id, "EVIDENCE_REJECTED", "Investigation", investigation_id, "Declared MIME does not match extension")
            self._finish(atomic)
            raise ValidationError("Declared MIME type is incompatible with the evidence extension.")
        parser = self.registry.select(filename, declared_mime)
        try:
            stored = self.storage.store_stream(upload.file)
        except Exception:
            self._audit(org_id, investigation_id, actor_id, "EVIDENCE_REJECTED", "Investigation", investigation_id, "Storage validation failed")
            self.db.commit()
            raise
        duplicate = self.repo.duplicate(org_id, investigation_id, stored.sha256)
        if duplicate is not None:
            self.storage.delete(stored.storage_key)
            self._audit(org_id, investigation_id, actor_id, "EVIDENCE_DUPLICATE", "EvidenceItem", duplicate.id, "Duplicate SHA-256 in investigation")
            self.db.commit()
            raise ConflictError("Duplicate evidence already exists in this investigation.")

        now = datetime.now(timezone.utc)
        evidence: EvidenceItem | None = None
        run: EvidenceParseRun | None = None
        try:
            evidence = EvidenceItem(
                org_id=org_id, investigation_id=investigation_id, original_filename=filename,
                storage_key=stored.storage_key, sha256=stored.sha256, byte_size=stored.byte_size,
                detected_mime=declared_mime or "application/octet-stream", extension=extension,
                acquisition_source=acquisition_source, imported_by_id=actor_id, imported_at=now,
                parsing_status="parsing",
            )
            self.db.add(evidence)
            self.db.flush()
            run = EvidenceParseRun(
                org_id=org_id, evidence_id=evidence.id, parser_name=parser.parser_id,
                parser_version=parser.parser_version, run_sequence=1, status="parsing", started_at=now,
            )
            self.db.add(run)
            self.db.flush()
            self._audit(org_id, investigation_id, actor_id, "EVIDENCE_ACCEPTED", "EvidenceItem", evidence.id, None)
            self._audit(org_id, investigation_id, actor_id, "PARSE_STARTED", "EvidenceParseRun", run.id, None)
            self._finish(atomic)
        except Exception:
            self.db.rollback()
            self.storage.delete(stored.storage_key)
            raise

        try:
            with self.storage.open_for_read(stored.storage_key) as source:
                try:
                    content = source.read().decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ValidationError("Evidence must be valid UTF-8 text.") from exc
            self._validate_json_depth(content, extension)
            records = parser.parse(content)
            self._validate_records(records)
            self._persist_facts(org_id, investigation_id, evidence, run, records)
            run.status = "complete"
            run.ended_at = datetime.now(timezone.utc)
            evidence.parsing_status = "complete"
            self._audit(org_id, investigation_id, actor_id, "PARSE_COMPLETED", "EvidenceParseRun", run.id, None)
            self._finish(atomic)
            return evidence
        except Exception as exc:
            self.db.rollback()
            if atomic:
                self.storage.delete(stored.storage_key)
                raise
            # The accepted original is retained, while all partial facts from
            # the failed transaction are rolled back before failure is visible.
            failed_evidence = self.db.get(EvidenceItem, evidence.id)
            failed_run = self.db.get(EvidenceParseRun, run.id)
            if failed_evidence is not None and failed_run is not None:
                failed_evidence.parsing_status = "failed"
                failed_run.status = "failed"
                failed_run.ended_at = datetime.now(timezone.utc)
                failed_run.error_summary = str(exc)[:2000]
                self._audit(org_id, investigation_id, actor_id, "PARSE_FAILED", "EvidenceParseRun", failed_run.id, str(exc)[:1000])
                self.db.commit()
            raise

    def _finish(self, atomic: bool) -> None:
        if atomic:
            self.db.flush()
        else:
            self.db.commit()

    def _validate_json_depth(self, content: str, extension: str) -> None:
        if extension != ".json":
            return
        import json
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return  # JsonParser emits the canonical malformed-input error.

        def depth(value, current=0):
            if current > self.settings.MAX_JSON_DEPTH:
                raise ValidationError("JSON evidence exceeds the nesting-depth limit.")
            if isinstance(value, dict):
                for child in value.values():
                    depth(child, current + 1)
            elif isinstance(value, list):
                for child in value:
                    depth(child, current + 1)
        depth(payload)

    def _validate_records(self, records: list[ParsedRecord]) -> None:
        if len(records) > self.settings.MAX_RAW_RECORDS:
            raise ValidationError("Evidence exceeds the raw-record limit.")
        events = sum(record.event is not None for record in records)
        if events > self.settings.MAX_EVENTS:
            raise ValidationError("Evidence exceeds the event limit.")
        if any(len(record.content.encode("utf-8")) > self.settings.MAX_RAW_RECORD_LENGTH for record in records):
            raise ValidationError("Evidence contains a raw record exceeding the length limit.")

    def _persist_facts(self, org_id: UUID, investigation_id: UUID, evidence: EvidenceItem, run: EvidenceParseRun, records: list[ParsedRecord]) -> None:
        indicator_count = entity_count = 0
        indicators: dict[tuple[str, str], Indicator] = {}
        entities: dict[tuple[str, str], Entity] = {}
        for ordinal, record in enumerate(records):
            raw = RawRecord(org_id=org_id, evidence_id=evidence.id, parse_run_id=run.id, ordinal=ordinal,
                            content=record.content, content_type=record.content_type, byte_offset=record.byte_offset,
                            line_start=record.line_start, line_end=record.line_end, encoding="utf-8")
            self.db.add(raw)
            self.db.flush()
            event = None
            if record.event is not None:
                e = record.event
                event = Event(org_id=org_id, investigation_id=investigation_id, evidence_id=evidence.id, raw_record_id=raw.id,
                              normalizer_name=self.registry.select(evidence.original_filename, evidence.detected_mime).parser_id,
                              normalizer_version=self.registry.select(evidence.original_filename, evidence.detected_mime).parser_version,
                              ordinal=0, timestamp=e.timestamp, source=e.source, host=e.host, user=e.user, process=e.process,
                              source_ip=e.source_ip, destination_ip=e.destination_ip, source_port=e.source_port,
                              destination_port=e.destination_port, event_type=e.event_type, action=e.action,
                              deterministic_severity=e.deterministic_severity, normalized=e.normalized)
                self.db.add(event)
                self.db.flush()
            for occurrence_ordinal, token in enumerate(extract_indicators(record.content)):
                indicator_count += 1
                if indicator_count > self.settings.MAX_EXTRACTED_INDICATORS:
                    raise ValidationError("Evidence exceeds the indicator extraction limit.")
                key = (token.type, token.normalized_value)
                indicator = indicators.get(key)
                if indicator is None:
                    indicator = self.db.query(Indicator).filter_by(org_id=org_id, type=token.type, normalized_value=token.normalized_value).one_or_none()
                    if indicator is None:
                        indicator = Indicator(org_id=org_id, type=token.type, normalized_value=token.normalized_value, display_value=token.normalized_value, first_seen_at=event.timestamp if event else None, last_seen_at=event.timestamp if event else None, occurrence_count=0)
                        self.db.add(indicator)
                        self.db.flush()
                    indicators[key] = indicator
                indicator.occurrence_count += 1
                self.db.add(IndicatorOccurrence(org_id=org_id, investigation_id=investigation_id, indicator_id=indicator.id,
                    evidence_id=evidence.id, raw_record_id=raw.id, event_id=event.id if event else None,
                    extractor_name="deterministic-regex", extractor_version="1.0.0", occurrence_ordinal=occurrence_ordinal,
                    observed_at=event.timestamp if event else None))
            record_entities: dict[tuple[str, str], Entity] = {}
            for occurrence_ordinal, candidate in enumerate(record.entities):
                canonical = self._canonical_entity(candidate)
                if canonical is None:
                    continue
                entity_count += 1
                if entity_count > self.settings.MAX_EXTRACTED_ENTITIES:
                    raise ValidationError("Evidence exceeds the entity extraction limit.")
                key = (candidate.type, canonical)
                entity = entities.get(key)
                if entity is None:
                    entity = self.db.query(Entity).filter_by(org_id=org_id, investigation_id=investigation_id, type=candidate.type, canonical_value=canonical).one_or_none()
                    if entity is None:
                        entity = Entity(org_id=org_id, investigation_id=investigation_id, type=candidate.type, canonical_value=canonical, display_name=candidate.display_name or candidate.value, first_seen_at=event.timestamp if event else None, last_seen_at=event.timestamp if event else None)
                        self.db.add(entity)
                        self.db.flush()
                    entities[key] = entity
                record_entities[key] = entity
                observation = EntityObservation(org_id=org_id, investigation_id=investigation_id, entity_id=entity.id,
                    evidence_id=evidence.id, raw_record_id=raw.id, event_id=event.id if event else None,
                    extractor_name="deterministic-parser", extractor_version="1.0.0", occurrence_ordinal=occurrence_ordinal,
                    observed_at=event.timestamp if event else None)
                self.db.add(observation)
                self.db.flush()
            for relationship_ordinal, link in enumerate(record.relationships):
                source_key = (link.source.type, self._canonical_entity(link.source) or "")
                target_key = (link.target.type, self._canonical_entity(link.target) or "")
                source, target = record_entities.get(source_key), record_entities.get(target_key)
                if source is None or target is None or source.id == target.id:
                    continue
                locator_hash = hashlib.sha256(f"{raw.id}:{relationship_ordinal}".encode()).hexdigest()
                self.db.add(EntityRelationship(org_id=org_id, investigation_id=investigation_id, source_entity_id=source.id,
                    target_entity_id=target.id, relationship_type=link.relationship_type, derivation_name="deterministic-parser",
                    derivation_version="1.0.0", evidence_id=evidence.id, raw_record_id=raw.id,
                    event_id=event.id if event else None, source_locator_hash=locator_hash, observed_at=event.timestamp if event else None))

    @staticmethod
    def _canonical_entity(candidate: EntityCandidate) -> str | None:
        value = candidate.value.strip()
        if not value:
            return None
        return value.lower() if candidate.type in {"domain", "user", "host", "process", "file"} else value

    def _audit(self, org_id, investigation_id, actor_id, action, target_type, target_id, rationale):
        self.db.add(AuditEvent(org_id=org_id, investigation_id=investigation_id, actor_id=actor_id,
            actor_type="user", action=action, target_type=target_type, target_id=target_id,
            occurred_at=datetime.now(timezone.utc), rationale=rationale))
