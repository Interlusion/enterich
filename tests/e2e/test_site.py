"""Enterich reaches the seeded site as the agent user (ITEM-004's first step): the
configured Host selects the site, and the agent's key opens its records."""

from tests.e2e.seed import Seed
from tests.integration.mcp import Session


def test_the_agent_reads_the_seeded_item(mcp: Session, seeded: Seed) -> None:
    assert mcp.call("get_item", {"item_code": seeded.item}).data["item_code"] == seeded.item


def test_the_agent_reads_the_seeded_customer(mcp: Session, seeded: Seed) -> None:
    assert mcp.call("get_customer", {"name": seeded.customer}).data["name"] == seeded.customer


def test_the_agent_reads_the_seeded_supplier(mcp: Session, seeded: Seed) -> None:
    assert mcp.call("get_supplier", {"name": seeded.supplier}).data["name"] == seeded.supplier
