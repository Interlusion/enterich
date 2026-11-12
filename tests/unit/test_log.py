"""REQ-002-PRS-NF008: one JSON object per line, also for library lines."""

import io
import json
import logging
import traceback

import pytest

from enterich import log


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


@pytest.mark.parametrize("separator", ["\x85", "\u2028", "\u2029"])
def test_a_unicode_line_separator_stays_inside_the_line(separator: str) -> None:
    # Readers that split on Unicode line boundaries, Python's splitlines among them,
    # would otherwise see two lines.
    stream = capture()
    log.event("operation", operation="get_item", arguments={"item_code": f"A{separator}B"})
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["arguments"] == {"item_code": f"A{separator}B"}


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


def fail(message: str = "boom") -> None:
    raise RuntimeError(message)


def test_exceptions_keep_their_type() -> None:
    stream = capture()
    try:
        fail()
    except RuntimeError:
        logging.getLogger("mcp.server").exception("failed")
    line = json.loads(stream.getvalue())
    assert line["exception"] == "RuntimeError"
    assert "boom" in line["traceback"]


def test_an_exception_never_raised_keeps_its_type() -> None:
    # A library may pass an exception instance that has no traceback.
    stream = capture()
    logging.getLogger("mcp.server").error("failed", exc_info=ValueError("v"))
    line = json.loads(stream.getvalue())
    assert line["exception"] == "ValueError"
    assert "ValueError: v" in line["traceback"]


def test_a_failure_is_an_error_line_with_the_cleaned_traceback() -> None:
    stream = capture()
    with pytest.raises(RuntimeError) as caught:
        fail("bad token s3cret")
    log.failure(caught.value, secrets=("s3cret",))
    line = json.loads(stream.getvalue())
    assert line["event"] == "error"
    assert line["level"] == "error"
    expected = "".join(traceback.format_exception(caught.value)).replace("s3cret", "***")
    assert line["traceback"] == expected
