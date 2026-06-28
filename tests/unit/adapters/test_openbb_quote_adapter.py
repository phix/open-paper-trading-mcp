"""Unit tests for the OpenBB-backed quote adapter (ADR 0002, phix/stockade#7).

``obb`` is fully mocked so these tests need no network and no provider keys.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.adapters.config import AdapterFactory
from app.adapters.openbb import DEFAULT_PROVIDER, OpenBBQuoteAdapter
from app.models.assets import Option, Stock
from app.models.quotes import Quote

pytestmark = pytest.mark.journey_market_data


def _make_adapter(quote_return=None, quote_side_effect=None) -> OpenBBQuoteAdapter:
    """Build an adapter with a fully mocked ``obb`` (no network, no keys)."""
    adapter = OpenBBQuoteAdapter()

    fake_obb = MagicMock()
    if quote_side_effect is not None:
        fake_obb.equity.price.quote.side_effect = quote_side_effect
    else:
        fake_obb.equity.price.quote.return_value = quote_return

    # Inject the mock and skip lazy import / credential application.
    adapter._obb = fake_obb
    adapter._credentials_applied = True
    return adapter


def _quote_row(**overrides):
    row = {
        "symbol": "AAPL",
        "last_price": 283.78,
        "bid": 285.6,
        "ask": 284.46,
        "bid_size": 2,
        "ask_size": 3,
        "volume": 261244321,
        "close": None,
        "prev_close": 275.15,
    }
    row.update(overrides)
    return row


def test_default_provider_is_yfinance() -> None:
    """Zero-key default provider lets the adapter work without API keys."""
    adapter = OpenBBQuoteAdapter()
    assert adapter._provider == DEFAULT_PROVIDER == "yfinance"


@pytest.mark.asyncio
async def test_get_quote_maps_obb_fields_to_quote() -> None:
    adapter = _make_adapter(
        quote_return=SimpleNamespace(results=[_quote_row()])
    )

    quote = await adapter.get_quote(Stock(symbol="AAPL"))

    assert isinstance(quote, Quote)
    assert quote.symbol == "AAPL"
    assert quote.price == 283.78
    assert quote.bid == 285.6
    assert quote.ask == 284.46
    assert quote.bid_size == 2
    assert quote.ask_size == 3
    assert quote.volume == 261244321
    adapter._obb.equity.price.quote.assert_called_once_with(
        "AAPL", provider="yfinance"
    )


@pytest.mark.asyncio
async def test_get_quote_falls_back_to_close_when_no_last_price() -> None:
    adapter = _make_adapter(
        quote_return=SimpleNamespace(
            results=[_quote_row(last_price=None, close=190.5)]
        )
    )

    quote = await adapter.get_quote(Stock(symbol="AAPL"))

    assert quote is not None
    assert quote.price == 190.5


@pytest.mark.asyncio
async def test_get_quote_returns_none_on_empty_results() -> None:
    adapter = _make_adapter(quote_return=SimpleNamespace(results=[]))

    quote = await adapter.get_quote(Stock(symbol="NOPE"))

    assert quote is None


@pytest.mark.asyncio
async def test_get_quote_swallows_provider_errors() -> None:
    """Provider rate-limit/auth/network errors must yield None, never leak raw."""
    adapter = _make_adapter(
        quote_side_effect=RuntimeError("429 Too Many Requests")
    )

    quote = await adapter.get_quote(Stock(symbol="AAPL"))

    assert quote is None


@pytest.mark.asyncio
async def test_get_quote_option_out_of_scope_returns_none() -> None:
    adapter = _make_adapter()
    option = Option(symbol="AAPL240119C00195000")

    quote = await adapter.get_quote(option)

    assert quote is None
    adapter._obb.equity.price.quote.assert_not_called()


@pytest.mark.asyncio
async def test_get_quotes_omits_failed_symbols() -> None:
    def quote_side_effect(symbol, provider):
        if symbol == "AAPL":
            return SimpleNamespace(results=[_quote_row(symbol="AAPL")])
        return SimpleNamespace(results=[])

    adapter = _make_adapter(quote_side_effect=quote_side_effect)

    good = Stock(symbol="AAPL")
    bad = Stock(symbol="NOPE")
    result = await adapter.get_quotes([good, bad])

    assert good in result
    assert bad not in result
    assert result[good].price == 283.78


@pytest.mark.asyncio
async def test_options_chain_methods_are_out_of_scope_noops() -> None:
    adapter = _make_adapter()

    assert await adapter.get_chain("AAPL") == []
    assert await adapter.get_options_chain("AAPL") is None
    assert adapter.get_expiration_dates("AAPL") == []


@pytest.mark.asyncio
async def test_get_market_hours_shape() -> None:
    adapter = _make_adapter()

    hours = await adapter.get_market_hours()

    assert hours["timezone"] == "America/New_York"
    assert hours["regular_open"] == "09:30"
    assert isinstance(hours["is_open"], bool)


def test_registered_in_adapter_factory() -> None:
    """QUOTE_ADAPTER_TYPE=openbb resolves to the OpenBB adapter (no network)."""
    factory = AdapterFactory()
    assert "openbb" in factory.config.adapter_types

    adapter = factory.create_adapter("openbb")
    assert isinstance(adapter, OpenBBQuoteAdapter)
