from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_core_mode_quickstart_is_explicit_and_avoids_demo_or_r4_inputs():
    guide = (ROOT / "docs/release/DEPLOYMENT_QUICKSTART.md").read_text(encoding="utf-8")
    required = (
        "Core-mode deployment quickstart",
        "materialize-runtime-secrets.sh",
        "docker compose --project-name aegis-core",
        "admin-bootstrap",
        "Settings → Security",
        "migration service is the sole writer",
        "head `0024`",
        "does not enable the `ollama`",
        "Production demo seeding and demo credentials are not supported.",
        "AI-suggested / not canonical",
        "down -v",
        "V1-B3",
    )
    for phrase in required:
        assert phrase in guide
    for prohibited in ("admin@aegis.demo", "ChangeMe123!", "admin@r4.example.com", "/tmp/aegis-r4-acceptance"):
        assert prohibited not in guide


def test_production_environment_template_remains_placeholder_only():
    template = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    assert "<production-db-user>" in template
    assert "<admin@example.invalid>" in template
    for prohibited in ("ChangeMe123!", "admin@aegis.demo", "admin@r4.example.com"):
        assert prohibited not in template
