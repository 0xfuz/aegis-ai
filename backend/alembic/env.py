from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.shared.base import Base

# Import every module's models here so Base.metadata is fully populated for
# autogenerate. As new modules (investigations, attack_graph, ...) are
# added in later phases, add their model imports below.
from app.modules.identity.infrastructure import models as identity_models  # noqa: F401
from app.modules.investigations.infrastructure import models as investigations_models  # noqa: F401
from app.modules.connectors.infrastructure import models as connectors_models  # noqa: F401
from app.modules.assets.infrastructure import models as assets_models  # noqa: F401
from app.modules.evidence.infrastructure import models as evidence_models  # noqa: F401
from app.modules.ai_reasoning.infrastructure import intelligence_models  # noqa: F401
from app.modules.alert_triage.infrastructure import models as alert_triage_models  # noqa: F401

config = context.config
settings = get_settings()
# ``ConfigParser`` treats a percent sign as interpolation syntax.  Production
# secret-file passwords are deliberately allowed to contain URL-escaped
# characters (for example ``%2B``), so escape percent signs only while placing
# the URL into Alembic's configuration.  ConfigParser resolves ``%%`` back to
# the original URL before SQLAlchemy connects.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
