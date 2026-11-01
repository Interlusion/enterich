"""server.json, Enterich's entry in the MCP Registry (ITEM-003), agrees with the image, the
version and the configuration guide."""

import json
import re
import tomllib
from typing import Any

from enterich.config import KNOWN

IMAGE = "ghcr.io/interlusion/enterich"
# | `ENTERICH_X` | yes | `default` | meaning |
ROW = re.compile(r"^\| `(ENTERICH_\w+)` \| (yes|no) \| ([^|]*) \| (.*) \|$", re.MULTILINE)


def server() -> dict[str, Any]:
    with open("server.json", encoding="utf-8") as file:
        return json.load(file)


def test_the_name_is_the_images_label() -> None:
    with open("Dockerfile", encoding="utf-8") as file:
        label = re.search(r'io\.modelcontextprotocol\.server\.name="([^"]+)"', file.read())
    assert label is not None
    assert server()["name"] == label[1]


def test_the_version_and_the_image_are_pyprojects() -> None:
    with open("pyproject.toml", "rb") as file:
        version = tomllib.load(file)["project"]["version"]
    entry = server()
    [package] = entry["packages"]
    assert entry["version"] == version
    assert package["identifier"] == f"{IMAGE}:{version}"


def test_the_description_fits_the_registry() -> None:
    assert len(server()["description"]) <= 100


def test_the_variables_are_the_configuration_guides() -> None:
    with open("docs/guides/configuration.md", encoding="utf-8") as file:
        rows = ROW.findall(file.read())
    guide = {
        name: {
            "isRequired": required == "yes",
            # A default in backticks is a value; one in words ("all operations") isn't
            "default": default.strip()[1:-1] if re.fullmatch(r"`[^`]+`", default.strip()) else None,
            "isSecret": "(secret)" in meaning,
        }
        for name, required, default, meaning in rows
    }
    [package] = server()["packages"]
    listed = {
        v["name"]: {
            "isRequired": v.get("isRequired", False),
            "default": v.get("default"),
            "isSecret": v.get("isSecret", False),
        }
        for v in package["environmentVariables"]
    }
    assert set(listed) == {f"ENTERICH_{name}" for name in KNOWN}
    assert listed == guide
