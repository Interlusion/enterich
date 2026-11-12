"""Start-up: REQ-002-PRS-NF005 (refusal), and the start line and log level of REQ-002-PRS-NF008."""

import json
import logging
from importlib.metadata import version

import pytest

from enterich import __main__, log, tools
from tests.fakes.settings import API_SECRET, ENV


def test_an_invalid_configuration_stops_enterich(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ENTERICH_ISSUER")
    monkeypatch.setenv("ENTERICH_CLOCK_LEEWAY", "120")
    with pytest.raises(SystemExit) as stopped:
        __main__.main()
    assert stopped.value.code == 2
    out = capsys.readouterr().out
    line = json.loads(out)
    assert line["event"] == "error"
    assert line["level"] == "error"
    assert line["exception"] == "ConfigError"
    assert line["problems"] == [
        "ENTERICH_ISSUER: required",
        "ENTERICH_CLOCK_LEEWAY: must be from 0 to 60",
    ]
    assert API_SECRET not in out


def test_start_logs_the_settings_and_runs_uvicorn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ENTERICH_HOST", "127.0.0.2")
    ran: dict[str, object] = {}
    monkeypatch.setattr(__main__.uvicorn, "run", lambda app, **kw: ran.update(kw, app=app))  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    __main__.main()
    line = json.loads(capsys.readouterr().out)
    assert line["event"] == "start"
    assert line["level"] == "info"
    assert line["warnings"] == []
    assert line["version"] == version("enterich")
    assert line["resource_url"] == ENV["ENTERICH_RESOURCE_URL"]
    assert line["issuer"] == ENV["ENTERICH_ISSUER"]
    assert line["client"] == ENV["ENTERICH_CLIENT_ID"]
    assert line["subject"] == ENV["ENTERICH_SUBJECT"]
    assert line["company"] == ENV["ENTERICH_COMPANY"]
    assert line["leeway"] == 5
    assert line["operations"] == list(tools.names())
    assert API_SECRET not in json.dumps(line)
    assert ran["app"] is not None
    assert callable(ran["app"])
    assert ran["host"] == "127.0.0.2"
    assert ran["port"] == 8000
    assert ran["log_config"] is None
    assert ran["access_log"] is False
    assert ran["proxy_headers"] is False
    assert ran["server_header"] is False


def test_start_carries_the_warnings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ENTERICH_ERPNEXT_URL", "http://erp.internal")
    monkeypatch.setenv("ENTERICH_TOOL", "list_items")
    monkeypatch.setattr(__main__.uvicorn, "run", lambda app, **kw: None)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    __main__.main()
    line = json.loads(capsys.readouterr().out)
    assert line["level"] == "warning"
    assert line["warnings"] == [
        "ENTERICH_TOOL is not a known variable and is ignored",
        "ENTERICH_ERPNEXT_URL uses http: the API key travels unencrypted",
    ]


def test_the_log_level_variable_filters_library_lines_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ENTERICH_LOG_LEVEL", "error")

    def serve(app: object, **kw: object) -> None:
        log.event("rejection", logging.WARNING, status=401)
        logging.getLogger("uvicorn.error").warning("noise")
        logging.getLogger("uvicorn.error").error("trouble")

    monkeypatch.setattr(__main__.uvicorn, "run", serve)
    __main__.main()
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [line["event"] for line in lines] == ["start", "rejection", "library"]
    assert lines[2]["message"] == "trouble"
