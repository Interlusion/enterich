"""JSON-lines logging to standard output (REQ-002-PRS-NF008).

Enterich's own lines carry an `event` and its fields. Lines from libraries and
the HTTP server go through the same formatter, as event `library`.
"""

import json
import logging
import sys
import traceback
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, TextIO

from enterich.config import LogLevel

LOGGER = "enterich"
LIBRARY_EVENT = "library"
MAX_MESSAGE = 300
# Line breaks to readers that split on Unicode line boundaries; json.dumps escapes
# the other control characters, but with ensure_ascii=False not these.
LINE_SEPARATORS = str.maketrans({c: f"\\u{ord(c):04x}" for c in "\x85\u2028\u2029"})


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields: dict[str, Any] = getattr(record, "fields", {})
        line: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "event": getattr(record, "event", LIBRARY_EVENT),
        }
        if line["event"] == LIBRARY_EVENT:
            line["logger"] = record.name
            line["message"] = record.getMessage()
        line.update(fields)
        if record.exc_info and record.exc_info[1] is not None:
            line.setdefault("exception", type(record.exc_info[1]).__name__)
            line.setdefault("traceback", self.formatException(record.exc_info))
        return json.dumps(line, ensure_ascii=False, default=str).translate(LINE_SEPARATORS)


def configure(level: LogLevel, stream: TextIO | None = None) -> None:
    """Route every logger, Enterich's and the libraries', through one JSON handler."""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)  # filters the libraries' lines only
    # Enterich's events always reach the handler: a record propagates to the root's
    # handlers whatever the root's level.
    logging.getLogger(LOGGER).setLevel(logging.DEBUG)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        library = logging.getLogger(name)
        library.handlers.clear()
        library.propagate = True


def event(name: str, level: int = logging.INFO, **fields: Any) -> None:
    """Write one line for an Enterich event."""
    logging.getLogger(LOGGER).log(level, name, extra={"event": name, "fields": fields})


def failure(exc: BaseException, secrets: Iterable[str] = (), **fields: Any) -> None:
    """Write the `error` line for an unexpected exception, with every secret replaced."""

    def clean(text: str) -> str:
        for secret in secrets:
            text = text.replace(secret, "***") if secret else text
        return text

    event(
        "error",
        logging.ERROR,
        **fields,
        exception=type(exc).__name__,
        message=clean(str(exc))[:MAX_MESSAGE],
        traceback=clean("".join(traceback.format_exception(exc))),
    )
