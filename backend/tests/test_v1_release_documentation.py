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
