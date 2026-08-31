"""Static safety contract for the operator-only runtime secret helper."""
from pathlib import Path


def test_materializer_is_allowlisted_atomic_and_never_destructive():
    text = (Path(__file__).parents[2] / "scripts/release/materialize-runtime-secrets.sh").read_text()
    assert "set -euo pipefail" in text and "--preflight-only" in text
    assert "ALLOWLIST=" in text and "mktemp" in text and "mv -f" in text
    assert "down -v" not in text and "docker system prune" not in text
    assert "postgres_password" in text and "jwt_signing_secret" in text
    assert "Refusing to overwrite" in text and "! -L" in text
