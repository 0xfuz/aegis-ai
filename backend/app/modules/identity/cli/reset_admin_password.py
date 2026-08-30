"""Internal production-only administrator password recovery command."""
from __future__ import annotations

import argparse
import getpass
import os
import stat
import sys
from pathlib import Path

from app.core.config import get_settings
from app.modules.identity.domain.bootstrap import ProductionAdminPasswordRecoveryService
from app.shared.database import SessionLocal
from app.shared.exceptions import AegisError


def _read_password_file(value: str) -> str:
    path = Path(value)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size < 1 or info.st_size > 4096:
        raise ValueError("Password file is invalid.")
    if info.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ValueError("Password file permissions are unsafe.")
    with path.open("r", encoding="utf-8") as handle:
        return handle.read().rstrip("\r\n")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Reset one production administrator password.", allow_abbrev=False)
    command.add_argument("--organization-slug", required=True)
    command.add_argument("--email", required=True)
    command.add_argument("--password-file")
    return command


def main(argv: list[str] | None = None, *, prompt=getpass.getpass) -> int:
    args = parser().parse_args(argv)
    db = None
    try:
        settings = get_settings()
        if settings.ENVIRONMENT.casefold() != "production" or settings.DEBUG or settings.SEED_DEMO_DATA:
            raise ValueError("Production recovery configuration is invalid.")
        if args.password_file:
            password = _read_password_file(args.password_file)
        else:
            password = prompt("New administrator password: ")
            if password != prompt("Confirm new administrator password: "):
                raise ValueError("Password confirmation does not match.")
        db = SessionLocal()
        ProductionAdminPasswordRecoveryService(
            db, environment=settings.ENVIRONMENT, demo_seed_enabled=settings.SEED_DEMO_DATA,
        ).reset(organization_slug=args.organization_slug, email=args.email, password=password)
        return 0
    except (AegisError, OSError, ValueError):
        return 2
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
