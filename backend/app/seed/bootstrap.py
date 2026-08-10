"""Explicit development/demo-only seed entrypoint."""
from app.core.config import get_settings
from app.seed.seed_data import seed


def seed_demo_if_enabled() -> bool:
    settings = get_settings()
    if not settings.SEED_DEMO_DATA:
        return False
    # Settings rejects this combination in production. Keep the guard here
    # as a second boundary in case configuration validation changes.
    if settings.ENVIRONMENT.lower() == "production":
        raise RuntimeError("Demo data seeding is prohibited in production.")
    seed()
    return True


if __name__ == "__main__":
    seed_demo_if_enabled()
