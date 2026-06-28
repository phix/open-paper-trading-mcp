"""Live OpenBB quote test (ADR 0002, phix/stockade#7).

Exercises the *real* ``OpenBBQuoteAdapter`` against OpenBB's keyless ``yfinance``
default provider — proving the Data-layer -> Hub seam works against real market
data, not just the mocked ``obb`` used by the unit tests and the deterministic
e2e smoke test (``test_e2e_openbb_backtrader_hub.py``).

Opt-in by design: marked ``integration`` + ``journey_integration`` + ``live_data``
so it stays out of the default unit pass (``pytest -m "not live_data"``). It needs
network access to yfinance but **no** API keys. If the quote can't be fetched
(no network, provider hiccup, market-closed illiquidity), the test SKIPS with a
clear reason rather than failing — a live data source must never flake the suite.
"""

from __future__ import annotations

import pytest

from app.adapters.openbb import DEFAULT_PROVIDER, OpenBBQuoteAdapter
from app.models.assets import Stock
from app.models.quotes import Quote

pytestmark = [
    pytest.mark.integration,
    pytest.mark.journey_integration,
    pytest.mark.live_data,
]


@pytest.mark.asyncio
async def test_openbb_live_quote_for_liquid_symbol() -> None:
    """A real AAPL quote comes back from OpenBB's keyless yfinance provider."""
    adapter = OpenBBQuoteAdapter()
    # Confirms the zero-key path: no credentials configured, yfinance default.
    assert adapter._provider == DEFAULT_PROVIDER == "yfinance"

    try:
        quote = await adapter.get_quote(Stock(symbol="AAPL"))
    except Exception as exc:  # network/provider unavailable -> opt-in, skip
        pytest.skip(f"OpenBB live quote unavailable: {exc}")

    if quote is None:
        pytest.skip("OpenBB returned no quote for AAPL (provider/network/closed)")

    # Real data: shape is a Hub Quote and the price is a sane positive number.
    assert isinstance(quote, Quote)
    assert quote.symbol == "AAPL"
    assert quote.price is not None
    assert quote.price > 0
