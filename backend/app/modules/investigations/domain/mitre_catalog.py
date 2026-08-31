"""Bounded display catalog; it does not grant MITRE mapping authority."""

MITRE_CATALOG_VERSION = "enterprise-attack-v14.1-display-subset"
MITRE_TECHNIQUE_NAMES: dict[str, str] = {
    "T1110": "Brute Force",
    "T1078": "Valid Accounts",
    "T1059": "Command and Scripting Interpreter",
    "T1003": "OS Credential Dumping",
}


def technique_name(technique_id: str) -> str | None:
    return MITRE_TECHNIQUE_NAMES.get(technique_id)
