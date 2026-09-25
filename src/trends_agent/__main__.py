"""Entry point: `uv run python -m trends_agent {slack,cli}`."""

import argparse
import sys

import structlog

from trends_agent.config import get_settings
from trends_agent.logging_setup import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trends-agent", description=__doc__)
    parser.add_argument("mode", choices=["slack", "cli"], help="which channel adapter to run")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = structlog.get_logger()

    # Adapters are implemented in later phases (CLI: phase 1, Slack: phase 3).
    log.error("adapter_not_implemented", mode=args.mode)
    return 1


if __name__ == "__main__":
    sys.exit(main())
