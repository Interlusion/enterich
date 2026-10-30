"""The published tool list (REQ-001-PRS-F006, REQ-001-PRS-NF002): it changes
only together with the area specs. Update with `uv run pytest --snapshot-update`
and review the diff of tests/snapshots/tools.json."""

from pathlib import Path
from typing import Any

from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.json import JSONSnapshotExtension
from syrupy.location import PyTestLocation
from syrupy.types import SnapshotIndex

from tests.fakes.erpnext import FakeErpnext
from tests.fakes.jwks import FakeJwks, Signer, token
from tests.integration.mcp import Session, client


class ToolsJson(JSONSnapshotExtension):
    @classmethod
    def dirname(cls, *, test_location: PyTestLocation) -> str:
        return str(Path(__file__).parent.parent / "snapshots")

    @classmethod
    def get_snapshot_name(cls, *, test_location: PyTestLocation, index: SnapshotIndex = 0) -> str:
        return "tools"


def test_the_tool_list_matches_the_snapshot(
    jwks: FakeJwks, signer: Signer, erpnext: FakeErpnext, snapshot: SnapshotAssertion
) -> None:
    with client(jwks, erpnext=erpnext) as c:
        listed: list[dict[str, Any]] = Session(c, token(signer)).tools()
    assert sorted(listed, key=lambda t: t["name"]) == snapshot(extension_class=ToolsJson)
