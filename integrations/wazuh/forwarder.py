"""Durable, stdlib-only Wazuh-to-Aegis delivery forwarder."""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class SpoolFullError(RuntimeError): pass
class ForwarderConfigError(ValueError): pass


def _read_ingest_secret_file(path_value: str) -> str:
    """Read a bounded manager-mounted secret without exposing its value."""
    path = Path(path_value)
    try:
        info = path.stat()
        if not path.is_file() or not 0 < info.st_size <= 4096:
            raise ValueError
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ForwarderConfigError("Invalid Wazuh ingest secret file.") from exc
    value = value[:-1] if value.endswith("\n") else value
    if not value or value.strip() != value:
        raise ForwarderConfigError("Invalid Wazuh ingest secret file.")
    return value


@dataclass(frozen=True)
class ForwarderConfig:
    base_url: str
    connector_id: str
    ingest_secret: str
    spool_dir: Path
    timeout_seconds: float = 10.0
    initial_delay_seconds: float = 5.0
    maximum_delay_seconds: float = 300.0
    maximum_retry_age_seconds: float = 86400.0
    maximum_attempts: int = 20
    maximum_spool_bytes: int = 100 * 1024 * 1024
    verify_tls: bool = True
    jitter_fraction: float = 0.2

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "ForwarderConfig":
        env = os.environ if environ is None else environ
        required = ("AEGIS_WAZUH_BASE_URL", "AEGIS_WAZUH_CONNECTOR_ID", "AEGIS_WAZUH_INGEST_SECRET_FILE", "AEGIS_WAZUH_SPOOL_DIR")
        missing = [key for key in required if not env.get(key)]
        if missing: raise ForwarderConfigError(f"Missing required configuration: {', '.join(missing)}")
        verify = env.get("AEGIS_WAZUH_VERIFY_TLS", "true").casefold() not in {"0", "false", "no"}
        return cls(env["AEGIS_WAZUH_BASE_URL"], env["AEGIS_WAZUH_CONNECTOR_ID"], _read_ingest_secret_file(env["AEGIS_WAZUH_INGEST_SECRET_FILE"]), Path(env["AEGIS_WAZUH_SPOOL_DIR"]),
            float(env.get("AEGIS_WAZUH_TIMEOUT_SECONDS", "10")), float(env.get("AEGIS_WAZUH_INITIAL_DELAY_SECONDS", "5")),
            float(env.get("AEGIS_WAZUH_MAX_DELAY_SECONDS", "300")), float(env.get("AEGIS_WAZUH_MAX_RETRY_AGE_SECONDS", "86400")),
            int(env.get("AEGIS_WAZUH_MAX_ATTEMPTS", "20")), int(env.get("AEGIS_WAZUH_MAX_SPOOL_BYTES", str(100 * 1024 * 1024))), verify)

    def endpoint(self) -> str:
        if not self.base_url.startswith("https://") and self.verify_tls:
            raise ForwarderConfigError("HTTPS is required unless AEGIS_WAZUH_VERIFY_TLS=false is explicitly configured for local development.")
        return f"{self.base_url.rstrip('/')}/api/v1/ingest/wazuh/v1/{self.connector_id}"


def _now() -> float: return time.time()
def _utc(timestamp: float) -> str: return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


class DurableSpool:
    """One atomically-written JSON record per deterministic payload digest."""
    def __init__(self, root: Path, maximum_bytes: int):
        self.root, self.maximum_bytes = root, maximum_bytes
        self.pending, self.quarantine = root / "pending", root / "quarantine"
        for directory in (self.root, self.pending, self.quarantine):
            directory.mkdir(parents=True, exist_ok=True); os.chmod(directory, 0o700)

    @staticmethod
    def record_id(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def enqueue(self, payload: dict[str, Any], now: float | None = None) -> str:
        if not isinstance(payload, dict): raise ValueError("Wazuh delivery payload must be a JSON object.")
        now = _now() if now is None else now; record_id = self.record_id(payload); path = self.pending / f"{record_id}.json"
        if path.exists(): return record_id
        record = {"record_id": record_id, "payload": payload, "created_at": now, "next_attempt_at": now, "attempt_count": 0, "last_error": None}
        encoded = self._encoded(record)
        if self.size_bytes() + len(encoded) > self.maximum_bytes: raise SpoolFullError("Wazuh pending spool byte limit reached.")
        self._atomic_write(path, encoded)
        return record_id

    def ready(self, now: float | None = None) -> list[tuple[Path, dict[str, Any]]]:
        now = _now() if now is None else now; ready = []
        for path in sorted(self.pending.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(record, dict) or not isinstance(record.get("payload"), dict): raise ValueError("invalid record")
            except (OSError, ValueError, json.JSONDecodeError):
                self.quarantine_path(path, "CORRUPT_RECORD", now); continue
            if record.get("next_attempt_at", now) <= now: ready.append((path, record))
        return ready

    def update(self, path: Path, record: dict[str, Any]) -> None: self._atomic_write(path, self._encoded(record))
    def remove(self, path: Path) -> None: path.unlink(missing_ok=True)
    def size_bytes(self) -> int: return sum(path.stat().st_size for path in self.pending.glob("*.json"))

    def quarantine_path(self, path: Path, reason: str, now: float | None = None, record: dict[str, Any] | None = None) -> None:
        now = _now() if now is None else now
        try: raw = path.read_text(encoding="utf-8")
        except OSError: raw = ""
        payload = record.get("payload") if isinstance(record, dict) else None
        item = {"quarantined_at": now, "reason": reason, "record": record, "raw_record": raw if payload is None else None}
        name = f"{path.stem}-{int(now * 1000)}.json"; self._atomic_write(self.quarantine / name, self._encoded(item)); self.remove(path)

    @staticmethod
    def _encoded(value: dict[str, Any]) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path); os.chmod(path, 0o600)
        finally:
            if temporary.exists(): temporary.unlink(missing_ok=True)


class WazuhForwarder:
    def __init__(self, config: ForwarderConfig, post: Callable[[str, bytes, dict[str, str], float, bool], int] | None = None, clock: Callable[[], float] = _now, jitter: Callable[[float, float], float] = random.uniform):
        self.config, self.spool, self.clock, self.jitter = config, DurableSpool(config.spool_dir, config.maximum_spool_bytes), clock, jitter
        self.post = post or self._post

    def submit(self, payload: dict[str, Any]) -> str: return self.spool.enqueue(payload, self.clock())
    def drain(self) -> None:
        for path, record in self.spool.ready(self.clock()): self._deliver(path, record)

    def _deliver(self, path: Path, record: dict[str, Any]) -> None:
        try: status = self.post(self.config.endpoint(), json.dumps(record["payload"], separators=(",", ":")).encode(), {"Content-Type": "application/json", "X-Ingest-Secret": self.config.ingest_secret}, self.config.timeout_seconds, self.config.verify_tls)
        except (TimeoutError, OSError, urllib.error.URLError): self._retry(path, record, "CONNECTION_OR_TIMEOUT"); return
        if status in {200, 201}: self.spool.remove(path); return
        if status == 429 or 500 <= status <= 599: self._retry(path, record, f"HTTP_{status}"); return
        self.spool.quarantine_path(path, f"HTTP_{status}", self.clock(), record)

    def _retry(self, path: Path, record: dict[str, Any], error: str) -> None:
        now = self.clock(); attempts = int(record.get("attempt_count", 0)) + 1
        if attempts >= self.config.maximum_attempts or now - float(record["created_at"]) >= self.config.maximum_retry_age_seconds:
            record.update(attempt_count=attempts, last_error=error); self.spool.quarantine_path(path, f"RETRY_EXHAUSTED:{error}", now, record); return
        delay = min(self.config.maximum_delay_seconds, self.config.initial_delay_seconds * (2 ** (attempts - 1)))
        delay *= 1 + self.jitter(-self.config.jitter_fraction, self.config.jitter_fraction)
        record.update(attempt_count=attempts, next_attempt_at=now + max(0, delay), last_error=error); self.spool.update(path, record)

    @staticmethod
    def _post(url: str, data: bytes, headers: dict[str, str], timeout: float, verify_tls: bool) -> int:
        # urllib verifies TLS by default. Insecure mode is an explicit local-dev opt-in.
        import ssl
        context = None if verify_tls else ssl._create_unverified_context()
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response: return response.status
        except urllib.error.HTTPError as exc: return exc.code


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1: raise SystemExit("usage: wazuh_forwarder.py /path/to/alert.json")
    with open(args[0], encoding="utf-8") as handle: payload = json.load(handle)
    forwarder = WazuhForwarder(ForwarderConfig.from_env()); forwarder.submit(payload); forwarder.drain(); return 0

if __name__ == "__main__": raise SystemExit(main())
