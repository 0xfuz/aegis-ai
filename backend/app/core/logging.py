import logging
import sys

from app.core.config import get_settings

settings = get_settings()


def configure_logging() -> None:
    """Configure root logging once at app startup.

    Production log shipping (to whatever the org uses — CloudWatch, Datadog,
    an ELK stack) is intentionally out of scope for the MVP: this just gets
    structured, leveled logs onto stdout, which any container log driver
    can pick up.
    """
    level = logging.DEBUG if settings.DEBUG else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # Quiet noisy third-party loggers unless we're actively debugging them.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING if not settings.DEBUG else logging.INFO)
