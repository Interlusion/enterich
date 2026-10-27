"""REQ-002-PRS-NF008: one JSON object per line, also for library lines."""

import io
import json
import logging

from erpel import log


def capture() -> io.StringIO:
    stream = io.StringIO()
    log.configure("DEBUG", stream)
    return stream


def test_an_event_is_one_json_line() -> None:
    stream = capture()
    log.event("operation", operation="get_item", arguments={"item_code": 'A"\n{"event":"x"}'})
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    line = json.loads(lines[0])
    assert line["event"] == "operation"
    assert line["level"] == "info"
    assert line["arguments"] == {"item_code": 'A"\n{"event":"x"}'}
    assert line["time"].endswith("+00:00")


def test_library_lines_are_json_too() -> None:
    stream = capture()
    logging.getLogger("uvicorn.error").warning("something %s", "odd")
    line = json.loads(stream.getvalue())
    assert line["event"] == "library"
    assert line["logger"] == "uvicorn.error"
    assert line["message"] == "something odd"


def test_the_level_filters_library_lines_only() -> None:
    stream = io.StringIO()
    log.configure("ERROR", stream)
    log.event("start", version="0")
    log.event("rejection", logging.WARNING, status=401)
    logging.getLogger("uvicorn.error").warning("noise")
    logging.getLogger("uvicorn.error").error("trouble")
    events = [json.loads(line)["event"] for line in stream.getvalue().splitlines()]
    assert events == ["start", "rejection", "library"]


def fail() -> None:
    raise RuntimeError("boom")


def test_exceptions_keep_their_type() -> None:
    stream = capture()
    try:
        fail()
    except RuntimeError:
        logging.getLogger("mcp.server").exception("failed")
    line = json.loads(stream.getvalue())
    assert line["exception"] == "RuntimeError"
    assert "boom" in line["traceback"]
