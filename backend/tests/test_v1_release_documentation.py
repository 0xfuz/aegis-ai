import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_v1_documents_are_present_truthful_and_safe():
    required = ["README.md", "LICENSE", "NOTICE", "CHANGELOG.md", "SECURITY.md", "docs/release/V1_0_RELEASE.md", "docs/release/DEPLOYMENT_QUICKSTART.md", "docs/release/LAUNCH_POSTS.md"]
    for path in required:
        assert (ROOT / path).is_file()
    readme = (ROOT / "README.md").read_text()
    assert "controlled pilot use" in readme and "Wazuh" in readme
    assert "admin@aegis.demo" not in readme and "ChangeMe123!" not in readme
    assert "Enterprise SIEM replacement" in readme and "Splunk" in readme
    license_text = (ROOT / "LICENSE").read_text()
    assert "Apache License" in license_text and "Version 2.0, January 2004" in license_text
    assert "0x0MAr" in (ROOT / "NOTICE").read_text()
    assert "security-contact@example.invalid" in (ROOT / "SECURITY.md").read_text()
    assert "not a final v1.0.0 announcement" in (ROOT / "docs/release/V1_0_RELEASE.md").read_text()


def test_release_docs_do_not_expose_runtime_markers():
    text = "\n".join((ROOT / path).read_text() for path in ["README.md", "CHANGELOG.md", "SECURITY.md", "docs/release/V1_0_RELEASE.md", "docs/release/DEPLOYMENT_QUICKSTART.md", "docs/release/LAUNCH_POSTS.md"])
    for marker in ("/tmp/aegis-r4", "aegis-r4-", "BEGIN PRIVATE KEY", "ChangeMe123!"):
        assert marker not in text


def test_v1_b3_failure_record_is_truthful_and_excludes_a_throughput_claim():
    text = (ROOT / "docs/release/V1_0_PILOT_PERFORMANCE.md").read_text()
    for phrase in ("V1-B3 STATUS: FAILED", "462cb6cc509e75062b4a53addc5452ec1e49a024", "280 returned and accepted requests", "five requests were still running", "FUTURE_COMPLETION_TIMEOUT", "NOT RUN", "V1-C and v1.0.0 remain blocked"):
        assert phrase in text
    assert re.search(r"Fifteen Futures were\s+cancelled", text)
    assert "No complete-workload p50/p95/p99 values" in text
    assert "no supported\nthroughput envelope" in text
