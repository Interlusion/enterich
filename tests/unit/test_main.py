"""Start-up: REQ-002-PRS-NF005 (refusal) and the start line of REQ-002-PRS-NF008."""

import json

import pytest

from erpel import __main__
from tests.fakes.settings import API_SECRET, ENV


def test_an_invalid_configuration_stops_erpel(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ERPEL_ISSUER")
    monkeypatch.setenv("ERPEL_CLOCK_LEEWAY", "120")
    with pytest.raises(SystemExit) as stopped:
        __main__.main()
    assert stopped.value.code == 2
    out = capsys.readouterr().out
    line = json.loads(out)
    assert line["event"] == "error"
    assert line["problems"] == [
        "ERPEL_ISSUER: required",
        "ERPEL_CLOCK_LEEWAY: must be from 0 to 60",
    ]
    assert API_SECRET not in out


def test_start_logs_the_settings_and_runs_uvicorn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    ran: dict[str, object] = {}
    monkeypatch.setattr(__main__.uvicorn, "run", lambda app, **kw: ran.update(kw))  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    __main__.main()
    line = json.loads(capsys.readouterr().out)
    assert line["event"] == "start"
    assert line["subject"] == ENV["ERPEL_SUBJECT"]
    assert line["leeway"] == 5
    assert API_SECRET not in json.dumps(line)
    assert ran["port"] == 8000
    assert ran["proxy_headers"] is False
    assert ran["server_header"] is False


def test_start_carries_the_warnings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ERPEL_ERPNEXT_URL", "http://erp.internal")
    monkeypatch.setenv("ERPEL_TOOL", "list_items")
    monkeypatch.setattr(__main__.uvicorn, "run", lambda app, **kw: None)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    __main__.main()
    line = json.loads(capsys.readouterr().out)
    assert line["level"] == "warning"
    assert line["warnings"] == [
        "ERPEL_TOOL is not a known variable and is ignored",
        "ERPEL_ERPNEXT_URL uses http: the API key travels unencrypted",
    ]
