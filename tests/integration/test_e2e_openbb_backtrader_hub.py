"""End-to-end smoke test for the Stockade loop: OpenBB quote -> backtrader
signal -> Hub paper order (issue phix/stockade#10; ADRs 0002 & 0003).

This proves the three integrated pieces *compose*:

* **Step 1 — Data layer (ADR 0002).** A quote is produced by the Hub's
  ``OpenBBQuoteAdapter``. ``obb`` is fully MOCKED here (same style as
  ``tests/unit/adapters/test_openbb_quote_adapter.py``) so the test is
  deterministic and needs no network or provider keys.
* **Step 2 — Strategy layer (ADR 0003).** That quote price feeds a minimal
  ``backtrader`` strategy whose orders are collected by the Stockade
  ``OrderIntentCollector`` analyzer into a fork-neutral ``OrderIntent``. This
  step runs LIVE against the real ``backtrader`` fork if it is importable;
  otherwise the whole test SKIPS with a clear reason (backtrader lives in a
  sibling fork with its own env, not the Hub's).
* **Step 3 — Hub (ADR 0003).** The ``OrderIntent`` is submitted through the
  real ``submit_intents`` + ``DedupeLedger`` onto the Hub's actual
  ``POST /api/v1/trading/orders`` endpoint via FastAPI's ``TestClient`` (a real,
  DB-backed simulated paper order — no mock at the HTTP boundary). Re-submitting
  asserts idempotency: the dedupe ledger prevents a duplicate paper trade.

  The Hub's order path validates the symbol by fetching a quote first. We point
  the Hub's ``TradingService`` at the *same* mocked ``OpenBBQuoteAdapter`` from
  step 1, so that symbol-validation quote is the OpenBB quote — deterministic and
  keyless. (The default synthetic ``test`` adapter is DB-backed and would need
  seeded per-date quote rows; using the OpenBB adapter keeps the loop honest:
  the OpenBB quote really is what the Hub sees.)

Paper-only by construction: the loop terminates at a Hub *simulated* order; there
is no brokerage path anywhere in this test.

--------------------------------------------------------------------------------
How to run it (full stack, true end-to-end)
--------------------------------------------------------------------------------
The Hub test suite has a session-scoped autouse fixture that needs Postgres on
:5432 and the async SQLAlchemy ``greenlet`` extra. backtrader is a sibling fork
not installed in the Hub env, so point ``STOCKADE_BACKTRADER_PATH`` (or
``PYTHONPATH``) at it. From the Hub fork root::

    # 1. Temp Postgres matching tests/conftest.py's TEST_DATABASE_URL
    docker run -d --rm --name stockade-e2e-pg \
        -e POSTGRES_USER=trading_user \
        -e POSTGRES_PASSWORD=trading_password \
        -e POSTGRES_DB=trading_db_test \
        -p 5432:5432 postgres:15-alpine

    # 2. async SQLAlchemy needs greenlet
    uv pip install greenlet

    # 3. Run this test with backtrader importable from its sibling fork
    STOCKADE_BACKTRADER_PATH=../backtrader \
        uv run pytest tests/integration/test_e2e_openbb_backtrader_hub.py -q

    # 4. Tidy up
    docker rm -f stockade-e2e-pg

Marked ``integration`` + ``journey_integration`` so it stays opt-in and does not
run in the default unit pass.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.adapters.openbb import OpenBBQuoteAdapter
from app.integrations.backtrader.order_intent import OrderIntent
from app.integrations.backtrader.submitter import DedupeLedger, submit_intents
from app.main import app
from app.models.assets import Stock

pytestmark = [pytest.mark.integration, pytest.mark.journey_integration]

# The submitter targets the Hub's full order path (``/api/v1/trading/orders``)
# itself, so callers pass the Hub's BASE host — in real use ``HUB_API_URL`` is the
# host root (e.g. ``http://localhost:2080``), not the router prefix. Under
# ``TestClient`` the base is empty (paths are relative). ``ORDERS_URL`` is the
# absolute route used for the GET assertions below.
HUB_BASE = ""
ORDERS_URL = "/api/v1/trading/orders"

# The symbol exercised through the whole loop. "AAPL" is also resolvable by the
# Hub's synthetic ``test`` quote adapter, which create_order uses to validate the
# symbol — so step 3 succeeds without any live market data.
SYMBOL = "AAPL"
QUANTITY = 10
# Deterministic quote price the mocked OpenBB adapter returns and that the
# backtrader bars carry, so the price genuinely flows quote -> strategy.
QUOTE_PRICE = 283.78


# --------------------------------------------------------------------------- #
# backtrader availability (sibling fork, not in the Hub env)
# --------------------------------------------------------------------------- #
def _import_backtrader():
    """Return the ``backtrader`` module or ``None`` if it cannot be imported.

    Tries a plain import first, then a sibling-fork path from
    ``STOCKADE_BACKTRADER_PATH`` or the conventional ``../backtrader`` relative to
    the Hub repo root. backtrader keeps its own per-fork env, so it is genuinely
    optional here.
    """
    try:
        return importlib.import_module("backtrader")
    except ImportError:
        pass

    candidates = []
    env_path = os.environ.get("STOCKADE_BACKTRADER_PATH")
    if env_path:
        candidates.append(Path(env_path))
    # Hub repo root is two parents up from this test file (tests/integration/).
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root.parent / "backtrader")

    for candidate in candidates:
        pkg_init = candidate / "backtrader" / "__init__.py"
        if pkg_init.exists():
            sys.path.insert(0, str(candidate))
            try:
                return importlib.import_module("backtrader")
            except ImportError:
                continue
    return None


bt = _import_backtrader()
requires_backtrader = pytest.mark.skipif(
    bt is None,
    reason=(
        "backtrader is a sibling fork not installed in the Hub env; set "
        "STOCKADE_BACKTRADER_PATH (or PYTHONPATH) to the backtrader fork to run "
        "this end-to-end test"
    ),
)


# --------------------------------------------------------------------------- #
# Step 1 helpers — OpenBB quote (obb mocked)
# --------------------------------------------------------------------------- #
def _mocked_openbb_adapter(price: float) -> OpenBBQuoteAdapter:
    """An ``OpenBBQuoteAdapter`` whose ``obb`` is mocked to return ``price``.

    Mirrors ``tests/unit/adapters/test_openbb_quote_adapter.py`` so step 1 needs
    no network and no provider credentials.
    """
    adapter = OpenBBQuoteAdapter()
    fake_obb = MagicMock()
    fake_obb.equity.price.quote.return_value = SimpleNamespace(
        results=[
            {
                "symbol": SYMBOL,
                "last_price": price,
                "bid": price - 0.01,
                "ask": price + 0.01,
                "bid_size": 2,
                "ask_size": 3,
                "volume": 1_000_000,
            }
        ]
    )
    adapter._obb = fake_obb
    adapter._credentials_applied = True
    return adapter


# --------------------------------------------------------------------------- #
# Step 2 helpers — backtrader strategy + analyzer -> OrderIntent
# --------------------------------------------------------------------------- #
def _build_price_feed(price: float):
    """A tiny in-memory backtrader data feed whose close == the OpenBB quote.

    Two bars so a market order placed on bar 1 has a following bar to submit
    against; the close on every bar is the OpenBB-sourced ``price``, so the quote
    genuinely drives the strategy's view of the market.
    """
    import pandas as pd

    index = pd.to_datetime(["2026-06-25", "2026-06-26"])
    frame = pd.DataFrame(
        {
            "open": [price, price],
            "high": [price, price],
            "low": [price, price],
            "close": [price, price],
            "volume": [1_000_000, 1_000_000],
            "openinterest": [0, 0],
        },
        index=index,
    )
    return bt.feeds.PandasData(dataname=frame)


def _make_intents_from_quote(price: float) -> list[OrderIntent]:
    """Run the minimal strategy through backtrader and collect ``OrderIntent``s.

    The strategy reads the OpenBB-sourced close and, on the first bar, emits a
    single market BUY. The Stockade ``OrderIntentCollector`` analyzer turns that
    backtrader order into a fork-neutral ``OrderIntent`` — no Hub import on the
    strategy side (ADR 0003's "produce intents only" boundary).
    """
    from app.integrations.backtrader.analyzer import get_collector_class

    captured_price: dict[str, float] = {}

    class _QuoteDrivenBuy(bt.Strategy):
        def __init__(self) -> None:
            self._fired = False

        def next(self) -> None:
            # The signal is a function of the (OpenBB-sourced) quote price.
            captured_price["close"] = float(self.data.close[0])
            if not self._fired and self.data.close[0] >= price:
                self.buy(size=QUANTITY)  # market order
                self._fired = True

    cerebro = bt.Cerebro()
    cerebro.addstrategy(_QuoteDrivenBuy)
    cerebro.adddata(_build_price_feed(price), name=SYMBOL)
    cerebro.addanalyzer(
        get_collector_class(), _name="order_intents", strategy_name="QuoteDrivenBuy"
    )
    strat = cerebro.run()[0]

    # Sanity: the price the strategy acted on is the OpenBB quote price.
    assert captured_price.get("close") == pytest.approx(price)
    return strat.analyzers.order_intents.intents()


# --------------------------------------------------------------------------- #
# Step 3 helpers — real Hub app + DB
# --------------------------------------------------------------------------- #
def _ensure_tables() -> None:
    """Create the Hub's tables in the (test) database if they don't exist.

    Idempotent ``create_all`` against the thread-local async engine, which the
    conftest points at ``TEST_DATABASE_URL``. Safe to run alongside conftest's
    own session-scoped table setup.
    """
    from app.models.database import trading  # noqa: F401  (register metadata)
    from app.models.database.base import Base
    from app.storage.database import get_async_engine

    async def _create() -> None:
        engine = get_async_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())


# --------------------------------------------------------------------------- #
# The end-to-end test
# --------------------------------------------------------------------------- #
@requires_backtrader
def test_openbb_quote_to_backtrader_signal_to_hub_paper_order(tmp_path, monkeypatch) -> None:
    """OpenBB quote -> backtrader OrderIntent -> Hub paper order, end to end."""
    # ---- Step 1: OpenBB quote (obb MOCKED) -------------------------------- #
    adapter = _mocked_openbb_adapter(QUOTE_PRICE)
    quote = asyncio.run(adapter.get_quote(Stock(symbol=SYMBOL)))
    assert quote is not None, "OpenBB adapter should return a quote"
    assert quote.symbol == SYMBOL
    assert quote.price == pytest.approx(QUOTE_PRICE)

    # ---- Step 2: backtrader signal -> OrderIntent (LIVE backtrader) ------- #
    intents = _make_intents_from_quote(quote.price)
    assert len(intents) == 1, f"expected one OrderIntent, got {intents}"
    intent = intents[0]
    assert intent.symbol == SYMBOL
    assert intent.side == "buy"
    assert intent.quantity == QUANTITY
    assert intent.order_type == "market"
    assert intent.limit_price is None
    # The intent maps 1:1 onto the Hub's OrderCreate body (ADR 0003), now
    # including the client_intent_id the Hub honors for idempotency.
    assert intent.to_order_create_payload() == {
        "symbol": SYMBOL,
        "order_type": "buy",
        "quantity": QUANTITY,
        "price": None,
        "condition": "market",
        "client_intent_id": intent.client_intent_id,
    }

    # ---- Step 3: submit to the real Hub paper-order endpoint (LIVE) ------- #
    _ensure_tables()
    ledger = DedupeLedger(tmp_path / "submitted.json")

    # ``with TestClient`` runs the app's lifespan so the container's real
    # TradingService is wired; then we point its quote adapter at the step-1
    # OpenBB-mocked adapter so symbol validation uses the OpenBB quote.
    from app.core.service_factory import get_trading_service

    with TestClient(app) as client:
        # monkeypatch so the global TradingService's quote adapter is restored at
        # teardown — otherwise this leaks the OpenBB adapter onto the singleton and
        # breaks later tests that rely on the default synthetic adapter.
        monkeypatch.setattr(get_trading_service(), "quote_adapter", adapter)

        orders_before = client.get(ORDERS_URL).json()["count"]

        result = submit_intents(
            intents, client=client, ledger=ledger, hub_url=HUB_BASE
        )
        assert result.ok, f"submission failed: {result.failed}"
        assert result.submitted == [intent.client_intent_id]
        assert result.skipped == []

        # A real, DB-backed paper order now exists in the Hub.
        after = client.get(ORDERS_URL).json()
        assert after["count"] == orders_before + 1
        created = [o for o in after["orders"] if o["symbol"] == SYMBOL]
        assert created, "expected the submitted paper order to be recorded"
        order = created[-1]
        assert order["quantity"] == QUANTITY
        assert order["order_type"] == "buy"
        assert order["condition"] == "market"
        assert order["status"] == "pending"  # simulated/paper, never a live fill

        # ---- Idempotency: re-running must NOT create a duplicate trade ---- #
        rerun = submit_intents(
            intents, client=client, ledger=ledger, hub_url=HUB_BASE
        )
        assert rerun.ok
        assert rerun.submitted == []
        assert rerun.skipped == [intent.client_intent_id]  # deduped via ledger

        final = client.get(ORDERS_URL).json()
        assert final["count"] == orders_before + 1, "re-submit must not duplicate"
