"""structlog configuration shared by all entry points."""

import logging

import structlog


def configure_logging(level: str = "INFO", json: bool = False) -> None:
    """Configure stdlib logging and structlog (console or JSON output)."""
    logging.basicConfig(format="%(message)s", level=level.upper())
    # Chatty third-party loggers: per-request HTTP lines and trafilatura extraction notes.
    for noisy in ("httpx", "httpx2", "trafilatura"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
    )
