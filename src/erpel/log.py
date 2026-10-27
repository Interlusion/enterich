"""JSON-lines logging to standard output (REQ-002-PRS-NF008).

Erpel's own lines carry an `event` and its fields. Lines from libraries and
the HTTP server go through the same formatter, as event `library`.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

from erpel.config import LogLevel

LOGGER = "erpel"
LIBRARY_EVENT = "library"


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
        return json.dumps(line, ensure_ascii=False, default=str)


def configure(level: LogLevel, stream: TextIO | None = None) -> None:
    """Route every logger, Erpel's and the libraries', through one JSON handler."""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)  # filters the libraries' lines only
    # Erpel's events always reach the handler: a record propagates to the root's
    # handlers whatever the root's level.
    logging.getLogger(LOGGER).setLevel(logging.DEBUG)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        library = logging.getLogger(name)
        library.handlers.clear()
        library.propagate = True


def event(name: str, level: int = logging.INFO, **fields: Any) -> None:
    """Write one line for an Erpel event."""
    logging.getLogger(LOGGER).log(level, name, extra={"event": name, "fields": fields})
