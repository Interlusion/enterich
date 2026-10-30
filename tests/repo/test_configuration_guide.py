"""The configuration guide names every variable Enterich reads (REQ-002-PRS-NF005)."""

from enterich.config import KNOWN


def test_the_configuration_guide_lists_every_variable() -> None:
    with open("docs/guides/configuration.md", encoding="utf-8") as guide:
        text = guide.read()
    for name in KNOWN:
        assert f"`ENTERICH_{name}`" in text
