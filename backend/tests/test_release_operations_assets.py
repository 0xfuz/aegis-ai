"""R3 operational assets are bounded, private, and fail closed by inspection."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_wazuh_operations_uses_verified_manager_conventions_and_secret_file_only():
    guide = (ROOT / "docs/release/WAZUH_OPERATIONS.md").read_text(encoding="utf-8")
    wrapper = (ROOT / "operations/wazuh/custom-aegis").read_text(encoding="utf-8")
    rule = (ROOT / "operations/wazuh/demo/aegis-agentless-demo.xml").read_text(encoding="utf-8")
    assert "4.9.2" in guide and "999:999" in guide and "/var/ossec/integrations" in guide
    assert "AEGIS_WAZUH_INGEST_SECRET_FILE" in guide and "decoded_as=syslog" in guide
    assert "AEGIS_WAZUH_INGEST_SECRET_FILE" in wrapper and "https://" in wrapper
    assert 'for candidate in "$@"' in wrapper and 'exec /usr/bin/python3 "$FORWARDER" "$ALERT_FILE"' in wrapper
    assert "100500" in rule and "AEGIS_R3_AGENTLESS_DEMO_LITERAL" in rule
    assert "decoded_as" not in rule
    assert "Vulnerability Detection" in guide and "vd_updater" in guide


def test_release_scripts_are_strict_and_restore_is_explicitly_isolated():
    backup = (ROOT / "scripts/release/backup-aegis.sh").read_text(encoding="utf-8")
    restore = (ROOT / "scripts/release/restore-aegis.sh").read_text(encoding="utf-8")
    scan = (ROOT / "scripts/release/scan-secrets.sh").read_text(encoding="utf-8")
    for script in (backup, restore, scan):
        assert "set -euo pipefail" in script
    assert "SHA256SUMS" in backup and "pending quarantine" in backup
    assert "--confirm-destructive-restore" in restore and "^aegis-restore-" in restore
    assert "docker compose down" not in restore and "docker rm" not in restore
    assert "git grep -IlE -e" in scan and "never prints a match" in scan


def test_backup_recovery_guide_excludes_host_secrets_and_describes_non_authoritative_redis():
    guide = (ROOT / "docs/release/BACKUP_AND_RECOVERY.md").read_text(encoding="utf-8")
    assert "does not archive Docker secrets" in guide
    assert "Redis is non-authoritative" in guide
    assert "aegis-restore-" in guide and "down -v" in guide


def test_backend_image_initializes_the_named_evidence_volume_for_the_unprivileged_api_user():
    dockerfile = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    assert "mkdir -p /app/storage/evidence" in dockerfile
    assert "chown -R aegis:aegis /app" in dockerfile
