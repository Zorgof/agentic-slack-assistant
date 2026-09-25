"""Entry point: `uv run python -m trends_agent {slack,cli}`."""

import argparse
import asyncio
import sys

import structlog

from trends_agent.config import get_settings
from trends_agent.logging_setup import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trends-agent", description=__doc__)
    parser.add_argument("mode", choices=["slack", "cli"], help="which channel adapter to run")
    parser.add_argument(
        "question", nargs="*", help="cli only: ask one question and exit (omit for interactive)"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = structlog.get_logger()

    if args.mode == "cli":
        from trends_agent.adapters.cli import run_cli

        return asyncio.run(run_cli(settings, " ".join(args.question) or None))

    # Slack adapter is implemented in phase 3.
    log.error("adapter_not_implemented", mode=args.mode)
    return 1


if __name__ == "__main__":
    sys.exit(main())
