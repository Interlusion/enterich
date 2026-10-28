"""The ERPNext client: REQ-002-PRS-NF006 (one credential), REQ-002-PRS-NF011
(limits), REQ-001-PRS-F008 (refusals reported)."""

import json
from collections.abc import AsyncIterator

import anyio
import pytest

from erpel import erpnext
from erpel.erpnext import Erpnext, ErpnextError
from tests.fakes.erpnext import FakeErpnext, error, item
from tests.fakes.settings import API_KEY, API_SECRET, settings

pytestmark = pytest.mark.anyio


@pytest.fixture
def fake() -> FakeErpnext:
    fake = FakeErpnext()
    fake.add("Item", item("SKU-1"))
    return fake


async def failure(fake: FakeErpnext, status: int, body: object) -> str:
    fake.fail("/api/method/frappe.client.get", status, body)
    with pytest.raises(ErpnextError) as caught:
        await Erpnext(settings(), fake.transport()).get_doc("Item", "SKU-1")
    return str(caught.value)


def test_the_limits_are_those_of_the_spec() -> None:
    assert erpnext.CALL_TIMEOUT == 30
    assert erpnext.MAX_RESPONSE_BYTES == 10 * 1024 * 1024


async def test_every_call_carries_the_agent_key_and_the_host(fake: FakeErpnext) -> None:
    client = Erpnext(settings(erpnext_host="erp.internal"), fake.transport())
    await client.get_doc("Item", "SKU-1")
    await client.get_list(
        "Item", fields=["item_code"], order_by="name asc", start=0, page_length=21
    )
    assert len(fake.received) == 2
    for received in fake.received:
        assert received.headers["authorization"] == f"token {API_KEY}:{API_SECRET}"
        assert received.headers["host"] == "erp.internal"


async def test_the_host_defaults_to_the_url_host(fake: FakeErpnext) -> None:
    await Erpnext(settings(), fake.transport()).get_doc("Item", "SKU-1")
    assert fake.received[0].headers["host"] == "127.0.0.1:8080"


async def test_cookies_from_erpnext_are_never_sent_back(fake: FakeErpnext) -> None:
    fake.set_cookie = True
    client = Erpnext(settings(), fake.transport())
    await client.get_doc("Item", "SKU-1")
    await client.get_doc("Item", "SKU-1")
    assert "cookie" not in fake.received[1].headers


async def test_a_redirect_is_a_refusal_not_a_second_request(fake: FakeErpnext) -> None:
    fake.redirect = True
    with pytest.raises(ErpnextError, match="redirect"):
        await Erpnext(settings(), fake.transport()).get_doc("Item", "SKU-1")
    assert len(fake.received) == 1


@pytest.fixture
async def local_erpnext() -> AsyncIterator[int]:
    """A minimal HTTP server on loopback, answering every request with an empty list."""
    listener = await anyio.create_tcp_listener(local_host="127.0.0.1", local_port=0)
    port = listener.extra(anyio.abc.SocketAttribute.local_port)

    async def answer(stream: anyio.abc.ByteStream) -> None:
        async with stream:
            await stream.receive(65536)
            body = b'{"data": []}'
            await stream.send(
                b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n"
                + f"content-length: {len(body)}\r\nconnection: close\r\n\r\n".encode()
                + body
            )

    async with anyio.create_task_group() as tg:
        tg.start_soon(listener.serve, answer)
        yield port
        tg.cancel_scope.cancel()


async def test_proxy_settings_in_the_environment_are_ignored(
    local_erpnext: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")  # nothing listens there
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    client = Erpnext(settings(erpnext_url=f"http://127.0.0.1:{local_erpnext}"))
    rows = await client.get_list(
        "Item", fields=["item_code"], order_by="name asc", start=0, page_length=1
    )
    assert rows == []


async def test_a_call_ends_after_the_call_timeout(
    fake: FakeErpnext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(erpnext, "CALL_TIMEOUT", 0.1)
    fake.delay = 1.0
    with anyio.fail_after(0.9), pytest.raises(ErpnextError, match="didn't answer"):
        await Erpnext(settings(), fake.transport()).get_doc("Item", "SKU-1")


async def test_a_response_over_10_mib_is_refused(fake: FakeErpnext) -> None:
    fake.huge_response = True
    with pytest.raises(ErpnextError, match="10 MiB"):
        await Erpnext(settings(), fake.transport()).get_doc("Item", "SKU-1")


@pytest.mark.parametrize(
    ("status", "exc_type", "message"),
    [
        (403, "PermissionError", "No permission for Item"),
        (417, "ValidationError", "Posting Date cannot be before the fiscal year"),
        (417, "LinkValidationError", "Could not find Customer: Nobody GmbH"),
        (417, "TimestampMismatchError", "Document has been modified after you have opened it"),
    ],
)
async def test_refusals_carry_status_type_and_message(
    fake: FakeErpnext, status: int, exc_type: str, message: str
) -> None:
    text = await failure(fake, status, error(status, exc_type, message))
    assert str(status) in text
    assert exc_type in text
    assert message in text
    assert "ERPNext's message" in text


async def test_html_is_removed_and_entities_decoded(fake: FakeErpnext) -> None:
    text = await failure(
        fake, 417, error(417, "ValidationError", "<b>Rate</b> &amp; <i>qty</i> &lt;0")
    )
    assert "Rate & qty <0" in text
    assert "<b>" not in text


@pytest.mark.parametrize("message", ["qty < 0 and rate > 5", "rate<0 or qty>5", "x <= 3"])
async def test_comparisons_are_not_taken_for_tags(fake: FakeErpnext, message: str) -> None:
    text = await failure(fake, 417, error(417, "ValidationError", message))
    assert f"ERPNext's message: {message}" in text


async def test_tracebacks_and_debug_output_are_not_forwarded(fake: FakeErpnext) -> None:
    body = error(417, "ValidationError", "Bad value", traceback="Traceback: SECRET-FRAME")
    body["_debug_messages"] = json.dumps(["DEBUG-OUTPUT"])
    text = await failure(fake, 417, body)
    assert "SECRET-FRAME" not in text
    assert "DEBUG-OUTPUT" not in text
    assert "frappe.exceptions" not in text


async def test_a_refusal_without_messages_carries_status_and_type(fake: FakeErpnext) -> None:
    text = await failure(fake, 417, {"exc_type": "ValidationError"})
    assert "417" in text
    assert "ValidationError" in text


async def test_a_refusal_is_at_most_300_characters(fake: FakeErpnext) -> None:
    text = await failure(fake, 417, error(417, "ValidationError", "x" * 2000))
    assert len(text) <= 300


async def test_a_refusal_that_isnt_json_still_reports_the_status(fake: FakeErpnext) -> None:
    fake.fail("/api/method/frappe.client.get", 502, None)
    with pytest.raises(ErpnextError, match="502"):
        await Erpnext(settings(), fake.transport()).get_doc("Item", "SKU-1")


async def test_a_deeply_nested_answer_isnt_json(fake: FakeErpnext) -> None:
    fake.raw = (200, b"[" * 100_000)
    with pytest.raises(ErpnextError, match="isn't JSON"):
        await Erpnext(settings(), fake.transport()).get_doc("Item", "SKU-1")


async def test_a_deeply_nested_refusal_still_reports_the_status(fake: FakeErpnext) -> None:
    fake.raw = (417, b"[" * 100_000)
    with pytest.raises(ErpnextError, match="417"):
        await Erpnext(settings(), fake.transport()).get_doc("Item", "SKU-1")


async def test_closing_the_client_closes_its_connections(fake: FakeErpnext) -> None:
    client = Erpnext(settings(), fake.transport())
    await client.aclose()
    with pytest.raises(RuntimeError):
        await client.get_doc("Item", "SKU-1")


@pytest.mark.parametrize("message", [{"columns": []}, {"result": None}, {"result": "rows"}])
async def test_a_report_answer_without_rows_is_refused(
    fake: FakeErpnext, message: dict[str, object]
) -> None:
    fake.fail("/api/method/frappe.desk.query_report.run", 200, {"message": message})
    with pytest.raises(ErpnextError, match="no result"):
        await Erpnext(settings(), fake.transport()).run_report("Accounts Receivable", {})


async def test_a_prepared_report_answer_passes_without_rows(fake: FakeErpnext) -> None:
    fake.prepared.add("Accounts Receivable")
    answer = await Erpnext(settings(), fake.transport()).run_report("Accounts Receivable", {})
    assert answer["prepared_report"] is True


async def test_the_fake_refuses_fields_v16_lacks(fake: FakeErpnext) -> None:
    client = Erpnext(settings(), fake.transport())
    with pytest.raises(ErpnextError, match="item_cod"):
        await client.get_list(
            "Item", fields=["item_cod"], order_by="name asc", start=0, page_length=1
        )
    with pytest.raises(ErpnextError, match="Dynamic Link"):
        await client.get_list(
            "Item",
            fields=["name"],
            filters=[["Dynamic Link", "link_name", "=", "x"]],
            order_by="name asc",
            start=0,
            page_length=1,
        )


async def test_refusal_texts_never_carry_the_credentials(fake: FakeErpnext) -> None:
    body = error(401, "AuthenticationError", f"token {API_KEY}:{API_SECRET} is invalid")
    text = await failure(fake, 401, body)
    assert API_KEY not in text
    assert API_SECRET not in text


async def test_the_client_counts_calls_and_their_time(fake: FakeErpnext) -> None:
    fake.delay = 0.05
    client = Erpnext(settings(), fake.transport())
    with erpnext.metered() as meter:
        await client.get_doc("Item", "SKU-1")
        await client.get_doc("Item", "SKU-1")
    assert meter.calls == 2
    assert meter.seconds >= 0.1
