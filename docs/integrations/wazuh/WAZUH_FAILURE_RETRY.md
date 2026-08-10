# Wazuh Forwarder Failure and Retry Semantics

Each pending spool record is a `0600` JSON file under a `0700` spool directory. Its deterministic filename is a SHA-256 digest of canonical JSON payload bytes. Records contain original payload, creation time, attempt count, next-attempt time, and last error—never connector secrets. Writes use a temporary `0600` file, `fsync`, and atomic rename.

`200` replayed and `201` accepted remove a record. Timeouts, connection errors, `429`, and `5xx` persist a bounded exponential retry with jitter. Default delay starts at 5 seconds, caps at 300 seconds, and ends at 20 attempts or 24 hours. Other `4xx` responses immediately move records to quarantine. Corrupt records and exhausted retries also move to quarantine.

Quarantine records preserve payload/record, reason, timestamp, and attempt count for operator inspection. There is no automatic resend from quarantine. Pending spool capacity is byte-bounded; a full spool fails loudly rather than silently dropping an alert. Events need not be globally ordered; retries retain payload identity and Aegis uses observed timestamps.
