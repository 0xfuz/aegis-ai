"""Create the initial administrator without accepting a password argument."""
from __future__ import annotations

import argparse
import getpass
import stat
from pathlib import Path

from app.core.config import get_settings
from app.modules.identity.domain.bootstrap import ProductionAdminBootstrapService
from app.shared.database import SessionLocal
from app.shared.exceptions import AegisError


def read_secret_file(path: str) -> str:
    target = Path(path)
    info = target.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 4096:
        raise ValueError("Invalid secret file.")
    value = target.read_text(encoding="utf-8")
    return value[:-1] if value.endswith("\n") else value


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Create one production administrator.", allow_abbrev=False)
    result.add_argument("--organization-name", required=True)
    result.add_argument("--organization-slug", required=True)
    result.add_argument("--email", required=True)
    result.add_argument("--full-name", required=True)
    result.add_argument("--password-file")
    return result


def main(argv: list[str] | None = None, *, prompt=getpass.getpass) -> int:
    args = parser().parse_args(argv)
    try:
        password = read_secret_file(args.password_file) if args.password_file else prompt("Initial administrator password: ")
        settings, db = get_settings(), SessionLocal()
        try:
            ProductionAdminBootstrapService(db, environment=settings.ENVIRONMENT, demo_seed_enabled=settings.SEED_DEMO_DATA).bootstrap(organization_name=args.organization_name, organization_slug=args.organization_slug, email=args.email, full_name=args.full_name, password=password)
        finally:
            db.close()
    except (AegisError, OSError, ValueError):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
