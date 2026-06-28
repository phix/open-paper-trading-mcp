"""Unit tests for the submitter + dedupe ledger (ADR 0003). HTTP is mocked, so
no running Hub / Postgres is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.integrations.backtrader.order_intent import OrderIntent
from app.integrations.backtrader.submitter import (
    DedupeLedger,
    submit_intents,
)


@dataclass
class FakeResponse:
    status_code: int
    body: Any = None

    def json(self) -> Any:
        return self.body if self.body is not None else {"success": True}


class RecordingClient:
    """Fake HttpClient capturing every POST; returns a configurable status."""

    def __init__(self, status_code: int = 200):
        self.status_code = status_code
        self.calls: list[tuple[str, Any]] = []

    def post(self, url: str, json: Any = None) -> FakeResponse:
        self.calls.append((url, json))
        return FakeResponse(self.status_code, {"success": True, "order": {"id": "o1"}})


def _intent(cid: str, symbol: str = "AAPL") -> OrderIntent:
    return OrderIntent(
        symbol=symbol,
        side="buy",
        quantity=1,
        order_type="market",
        limit_price=None,
        client_intent_id=cid,
        strategy="S",
    )


def test_submits_each_intent_once(tmp_path):
    ledger = DedupeLedger(tmp_path / "ledger.json")
    client = RecordingClient(200)
    intents = [_intent("a"), _intent("b", "MSFT")]

    result = submit_intents(
        intents, client=client, ledger=ledger, hub_url="http://hub:2080"
    )

    assert result.ok
    assert result.submitted == ["a", "b"]
    assert len(client.calls) == 2
    # Posts to the Hub's real order path with the mapped OrderCreate body.
    url, payload = client.calls[0]
    assert url == "http://hub:2080/api/v1/trading/orders"
    assert payload == {
        "symbol": "AAPL",
        "order_type": "buy",
        "quantity": 1,
        "price": None,
        "condition": "market",
        "client_intent_id": "a",
    }


def test_dedup_skips_already_submitted_in_same_batch_state(tmp_path):
    """Re-submitting the SAME export must not double-POST."""
    ledger_path = tmp_path / "ledger.json"
    intents = [_intent("a"), _intent("b", "MSFT")]

    # First run submits both.
    client1 = RecordingClient(200)
    r1 = submit_intents(
        intents, client=client1, ledger=DedupeLedger(ledger_path), hub_url="http://h"
    )
    assert r1.submitted == ["a", "b"]
    assert len(client1.calls) == 2

    # Second run with a FRESH ledger loaded from disk: nothing is re-posted.
    client2 = RecordingClient(200)
    r2 = submit_intents(
        intents, client=client2, ledger=DedupeLedger(ledger_path), hub_url="http://h"
    )
    assert r2.submitted == []
    assert r2.skipped == ["a", "b"]
    assert client2.calls == []  # zero HTTP calls -> no duplicate paper trades


def test_ledger_persists_across_instances(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = DedupeLedger(path)
    ledger.add("k1")
    reloaded = DedupeLedger(path)
    assert "k1" in reloaded
    assert len(reloaded) == 1


def test_failed_submit_not_recorded_so_it_retries(tmp_path):
    ledger_path = tmp_path / "ledger.json"
    intents = [_intent("a")]

    # Hub rejects with 400 -> not added to ledger.
    client_fail = RecordingClient(400)
    r1 = submit_intents(
        intents,
        client=client_fail,
        ledger=DedupeLedger(ledger_path),
        hub_url="http://h",
    )
    assert not r1.ok
    assert r1.failed and r1.failed[0][0] == "a"

    # Next run retries it (ledger never recorded the failure).
    client_ok = RecordingClient(200)
    r2 = submit_intents(
        intents, client=client_ok, ledger=DedupeLedger(ledger_path), hub_url="http://h"
    )
    assert r2.submitted == ["a"]
    assert len(client_ok.calls) == 1


def test_transport_error_is_captured_as_failure(tmp_path):
    class BoomClient:
        def post(self, url: str, json: Any = None):
            raise ConnectionError("hub unreachable")

    ledger = DedupeLedger(tmp_path / "ledger.json")
    result = submit_intents(
        [_intent("a")], client=BoomClient(), ledger=ledger, hub_url="http://h"
    )
    assert not result.ok
    assert "transport error" in result.failed[0][1]
    assert "a" not in ledger  # retryable on next run
