"""Unit tests for the OrderIntent contract and its mapping to the Hub's
``OrderCreate`` (ADR 0003). No running Hub, no backtrader required.
"""

from __future__ import annotations

import pytest

from app.integrations.backtrader.order_intent import (
    OrderIntent,
    make_client_intent_id,
)
from app.schemas.orders import OrderCondition, OrderCreate, OrderType


def _market_buy() -> OrderIntent:
    return OrderIntent(
        symbol="AAPL",
        side="buy",
        quantity=10,
        order_type="market",
        limit_price=None,
        client_intent_id="cid-1",
        strategy="SmaCross",
    )


def _limit_sell() -> OrderIntent:
    return OrderIntent(
        symbol="MSFT",
        side="sell",
        quantity=5,
        order_type="limit",
        limit_price=321.50,
        client_intent_id="cid-2",
        strategy="SmaCross",
    )


def test_market_intent_maps_to_ordercreate_payload():
    payload = _market_buy().to_order_create_payload()
    assert payload == {
        "symbol": "AAPL",
        "order_type": "buy",
        "quantity": 10,
        "price": None,
        "condition": "market",
    }


def test_limit_intent_maps_to_ordercreate_payload():
    payload = _limit_sell().to_order_create_payload()
    assert payload == {
        "symbol": "MSFT",
        "order_type": "sell",
        "quantity": 5,
        "price": 321.50,
        "condition": "limit",
    }


def test_payload_validates_as_real_hub_ordercreate_market():
    """The payload must be accepted by the Hub's actual Pydantic model."""
    model = OrderCreate(**_market_buy().to_order_create_payload())
    assert model.symbol == "AAPL"
    assert model.order_type == OrderType.BUY
    assert model.condition == OrderCondition.MARKET
    assert model.quantity == 10
    assert model.price is None


def test_payload_validates_as_real_hub_ordercreate_limit():
    model = OrderCreate(**_limit_sell().to_order_create_payload())
    assert model.order_type == OrderType.SELL
    assert model.condition == OrderCondition.LIMIT
    assert model.price == pytest.approx(321.50)


def test_client_intent_id_and_strategy_are_not_ordercreate_fields():
    """Documented mismatch: OrderCreate has no idempotency/strategy field."""
    payload = _market_buy().to_order_create_payload()
    assert "client_intent_id" not in payload
    assert "strategy" not in payload
    assert "client_intent_id" not in OrderCreate.model_fields
    assert "strategy" not in OrderCreate.model_fields


def test_round_trip_dict():
    intent = _limit_sell()
    assert OrderIntent.from_dict(intent.to_dict()) == intent


@pytest.mark.parametrize(
    "kwargs",
    [
        {"side": "hold"},
        {"order_type": "stop"},
        {"quantity": 0},
        {"quantity": -3},
    ],
)
def test_invalid_intents_rejected(kwargs):
    base = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10,
        "order_type": "market",
        "limit_price": None,
        "client_intent_id": "x",
        "strategy": "S",
    }
    base.update(kwargs)
    with pytest.raises(ValueError):
        OrderIntent(**base)


def test_limit_requires_price_and_market_forbids_price():
    with pytest.raises(ValueError):
        OrderIntent(
            symbol="AAPL",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=None,
            client_intent_id="x",
            strategy="S",
        )
    with pytest.raises(ValueError):
        OrderIntent(
            symbol="AAPL",
            side="buy",
            quantity=1,
            order_type="market",
            limit_price=100.0,
            client_intent_id="x",
            strategy="S",
        )


def test_client_intent_id_is_stable_and_not_random():
    a = make_client_intent_id(
        strategy="SmaCross",
        symbol="AAPL",
        side="buy",
        order_type="market",
        quantity=10,
        limit_price=None,
        timestamp="2024-01-02T00:00:00",
    )
    b = make_client_intent_id(
        strategy="SmaCross",
        symbol="AAPL",
        side="buy",
        order_type="market",
        quantity=10,
        limit_price=None,
        timestamp="2024-01-02T00:00:00",
    )
    assert a == b  # deterministic across calls (no random UUID)
    # Different triggering bar -> different id.
    c = make_client_intent_id(
        strategy="SmaCross",
        symbol="AAPL",
        side="buy",
        order_type="market",
        quantity=10,
        limit_price=None,
        timestamp="2024-01-03T00:00:00",
    )
    assert a != c
    assert a.startswith("SmaCross:AAPL:")
