import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_v1_documents_are_present_truthful_and_safe():
    required = ["README.md", "LICENSE", "NOTICE", "CHANGELOG.md", "CONTRIBUTING.md", "docs/ARCHITECTURE.md", "docs/release/V1_0_RELEASE.md", "docs/release/DEPLOYMENT_QUICKSTART.md", "docs/release/LOCAL_AI_EVALUATOR_GUIDE.md", "docs/release/WAZUH_EVALUATOR_GUIDE.md", "docs/release/PRIVATE_EVALUATOR_CHECKLIST.md", "docs/release/LAUNCH_POSTS.md"]
    for path in required:
        assert (ROOT / path).is_file()
    readme = (ROOT / "README.md").read_text()
    assert "controlled pilot use" in readme and "Wazuh" in readme
    assert "admin@aegis.demo" not in readme and "ChangeMe123!" not in readme
    assert "Enterprise SIEM replacement" in readme and "Splunk" in readme
    assert "independent personal project" in readme
    assert "not an official Wazuh product" in readme
    assert "Choose your path" in readme
    assert "280 of 300" in readme
    license_text = (ROOT / "LICENSE").read_text()
    assert "Apache License" in license_text and "Version 2.0, January 2004" in license_text
    assert "0x0MAr" in (ROOT / "NOTICE").read_text()
    assert not (ROOT / "SECURITY.md").exists()
    assert "not a final v1.0.0 announcement" in (ROOT / "docs/release/V1_0_RELEASE.md").read_text()


def test_release_docs_do_not_expose_runtime_markers():
    text = "\n".join((ROOT / path).read_text() for path in ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "docs/ARCHITECTURE.md", "docs/release/V1_0_RELEASE.md", "docs/release/DEPLOYMENT_QUICKSTART.md", "docs/release/LOCAL_AI_EVALUATOR_GUIDE.md", "docs/release/WAZUH_EVALUATOR_GUIDE.md", "docs/release/PRIVATE_EVALUATOR_CHECKLIST.md", "docs/release/LAUNCH_POSTS.md"])
    for marker in ("/tmp/aegis-r4", "aegis-r4-", "BEGIN PRIVATE KEY", "ChangeMe123!"):
        assert marker not in text


def test_private_evaluator_onboarding_keeps_core_mode_bounded_and_truthful():
    quickstart = (ROOT / "docs/release/DEPLOYMENT_QUICKSTART.md").read_text()
    checklist = (ROOT / "docs/release/PRIVATE_EVALUATOR_CHECKLIST.md").read_text()
    for phrase in (
        "Core mode starts only PostgreSQL, Redis, migration, API, and frontend.",
        "up -d --build postgres redis",
        "up --build migrate",
        "up -d --build api frontend",
        "logs --tail=50 api frontend",
        "Settings → Security",
        "Troubleshooting",
        "Wazuh connector or TLS is absent",
    ):
        assert phrase in quickstart
    for phrase in (
        "no fixed administrator account",
        "AI-suggested MITRE techniques are not",
        "did not complete 300/300 events at five events",
    ):
        assert phrase in checklist


def test_root_ignore_rules_exclude_operator_material_and_keep_safe_examples():
    ignore = (ROOT / ".gitignore").read_text()
    dockerignore = (ROOT / ".dockerignore").read_text()
    for phrase in (".env.production", "runtime-secrets/", "secrets/", "*.pem", "*.key", "*.junit.xml"):
        assert phrase in ignore
    for phrase in (".env.production", "runtime-secrets/", "secrets/", "*.pem", "*.key", "test-results/"):
        assert phrase in dockerignore


def test_optional_evaluator_guides_reuse_bounded_existing_contracts_only():
    readme = (ROOT / "README.md").read_text()
    quickstart = (ROOT / "docs/release/DEPLOYMENT_QUICKSTART.md").read_text()
    ai_guide = (ROOT / "docs/release/LOCAL_AI_EVALUATOR_GUIDE.md").read_text()
    wazuh_guide = (ROOT / "docs/release/WAZUH_EVALUATOR_GUIDE.md").read_text()
    compose = (ROOT / "docker-compose.production.yml").read_text()

    assert "LOCAL_AI_EVALUATOR_GUIDE.md" in readme
    assert "WAZUH_EVALUATOR_GUIDE.md" in readme
    assert "LOCAL_AI_EVALUATOR_GUIDE.md" in quickstart
    assert "WAZUH_EVALUATOR_GUIDE.md" in quickstart
    for flag in ("INTELLIGENCE_EXECUTION_ENABLED", "INTELLIGENCE_DISPATCH_ENABLED", "INTELLIGENCE_PROVIDER_ENABLED"):
        assert f"{flag}=true" in ai_guide
        assert f"{flag}: ${{{flag}:-false}}" in compose
    assert "llama3.2:latest" in ai_guide
    assert "--profile ollama" in ai_guide
    assert "Claims are not FACTs" in ai_guide
    assert "POST /api/v1/connectors/webhook" in wazuh_guide
    assert "settings:manage_connectors" in wazuh_guide
    assert "AEGIS_WAZUH_VERIFY_TLS=true" in wazuh_guide
    for prohibited in ("AEGIS_WAZUH_VERIFY_TLS=false", "down -v", "docker system prune", "ChangeMe123!", "admin@r4.example.com", "ollama pull"):
        assert prohibited not in ai_guide + wazuh_guide
    for phrase in ("documentation only", "owner walkthrough remains required"):
        assert phrase in ai_guide
    assert "documentation only" in wazuh_guide


def test_v1_b3_failure_record_is_truthful_and_excludes_a_throughput_claim():
    text = (ROOT / "docs/release/V1_0_PILOT_PERFORMANCE.md").read_text()
    for phrase in ("V1-B3 STATUS: FAILED", "462cb6cc509e75062b4a53addc5452ec1e49a024", "280 returned and accepted requests", "five requests were still running", "FUTURE_COMPLETION_TIMEOUT", "NOT RUN", "V1-C and v1.0.0 remain blocked"):
        assert phrase in text
    assert re.search(r"Fifteen Futures were\s+cancelled", text)
    assert "No complete-workload p50/p95/p99 values" in text
    assert "no supported\nthroughput envelope" in text
