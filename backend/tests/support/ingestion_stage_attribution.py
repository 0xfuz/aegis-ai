"""Test-only aggregate SQL/session attribution for the Wazuh webhook path.

This module is intentionally confined to ``backend/tests``. It inspects stack
frames in memory only to select a fixed stage label; it never stores a frame,
SQL text, parameter, payload, path, identity, or credential.
"""
from __future__ import annotations

import inspect
from collections import defaultdict
from contextlib import contextmanager
from time import monotonic
from typing import Any, Iterator

from sqlalchemy import event
from sqlalchemy.orm import Session

STAGES = ("authentication", "raw_event", "canonical_alert", "deduplication", "correlation_v2", "triage", "response_or_framework", "unattributed")
COUNTERS = ("select", "insert", "update", "delete", "other", "flush", "commit", "rollback", "transaction_begin", "transaction_end", "refresh")


def classify_frames(frames: list[Any] | None = None) -> str:
    """Return one fixed stage label using inner-domain precedence."""
    frames = inspect.stack() if frames is None else frames
    modules = [getattr(getattr(frame, "frame", frame), "f_globals", {}).get("__name__", "") for frame in frames]
    joined = " ".join(modules)
    for needle, label in (("correlation_v2_service", "correlation_v2"), ("triage_service", "triage"), ("deduplication_service", "deduplication"), ("alert_triage.domain.service", "canonical_alert"), ("webhook_service", "raw_event"), ("connectors.domain.service", "authentication"), ("connectors.api.router", "response_or_framework")):
        if needle in joined:
            return label
    return "unattributed"


class StageAttribution:
    def __init__(self, engine: Any):
        self.engine, self.installed, self.started = engine, False, 0.0
        self.counts = {stage: {counter: 0 for counter in COUNTERS} for stage in STAGES}

    def _stage(self) -> str: return classify_frames()
    def _inc(self, counter: str) -> None: self.counts[self._stage()][counter] += 1
    def _sql(self, _conn: Any, _cursor: Any, statement: str, _params: Any, _context: Any, _many: Any) -> None:
        word = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        self._inc({"SELECT": "select", "INSERT": "insert", "UPDATE": "update", "DELETE": "delete"}.get(word, "other"))
    def _flush(self, *_: Any) -> None: self._inc("flush")
    def _commit(self, *_: Any) -> None: self._inc("commit")
    def _rollback(self, *_: Any) -> None: self._inc("rollback")
    def _begin(self, *_: Any) -> None: self._inc("transaction_begin")
    def _end(self, *_: Any) -> None: self._inc("transaction_end")
    def _refresh(self, *_: Any) -> None: self._inc("refresh")
    def install(self) -> None:
        if self.installed: return
        self.started = monotonic()
        event.listen(self.engine, "before_cursor_execute", self._sql)
        for name, callback in (("after_flush", self._flush), ("after_commit", self._commit), ("after_rollback", self._rollback), ("after_begin", self._begin), ("after_transaction_end", self._end), ("refresh", self._refresh)):
            event.listen(Session, name, callback)
        self.installed = True
    def remove(self) -> None:
        if not self.installed: return
        event.remove(self.engine, "before_cursor_execute", self._sql)
        for name, callback in (("after_flush", self._flush), ("after_commit", self._commit), ("after_rollback", self._rollback), ("after_begin", self._begin), ("after_transaction_end", self._end), ("refresh", self._refresh)):
            event.remove(Session, name, callback)
        self.installed = False
    def totals(self) -> dict[str, int]: return {counter: sum(row[counter] for row in self.counts.values()) for counter in COUNTERS}
    def reconcile(self, whole: dict[str, int]) -> bool: return all(self.totals()[key] == whole.get(key, 0) for key in COUNTERS)

