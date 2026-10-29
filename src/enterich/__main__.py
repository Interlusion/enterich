"""Entry point: `enterich` or `python -m enterich`."""

import logging
import os
import sys
from importlib.metadata import version

import uvicorn

from enterich import log, tools
from enterich.app import create_app
from enterich.config import ConfigError, load


def main() -> None:
    try:
        settings = load(os.environ, tools.names())
    except ConfigError as exc:
        log.configure("INFO")
        log.event("error", logging.ERROR, exception="ConfigError", problems=exc.problems)
        sys.exit(2)

    log.configure(settings.log_level)
    log.event(
        "start",
        logging.WARNING if settings.warnings else logging.INFO,
        version=version("enterich"),
        resource_url=settings.resource_url,
        issuer=settings.issuer,
        client=settings.client_id,
        subject=settings.subject,
        company=settings.company,
        leeway=settings.clock_leeway,
        operations=list(settings.tools),
        warnings=list(settings.warnings),
    )
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
