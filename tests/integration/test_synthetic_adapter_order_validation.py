"""Regression test for phix/stockade#13.

``POST /api/v1/trading/orders`` must succeed with the *default* synthetic
``test`` quote adapter (``app.adapters.synthetic_data.DevDataQuoteAdapter``),
which reads quotes from the database via a **synchronous** SQLAlchemy session
during symbol validation.

Before the fix this raised
``greenlet_spawn has not been called; can't call await_only() here`` because the
sync engine was bound to the async ``asyncpg`` driver (and then, once that was
corrected, ``DetachedInstanceError`` because the sync session expired ORM rows on
commit). The #10 end-to-end test sidestepped the whole path by injecting the
OpenBB adapter; this test exercises the synthetic adapter directly so the
regression cannot creep back in.

Needs Postgres on :5432 and the async SQLAlchemy ``greenlet`` extra, like the
rest of the Hub suite (see ``tests/conftest.py``). Marked ``integration`` so it
stays opt-in alongside the other DB-backed integration tests.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.adapters.synthetic_data import DevDataQuoteAdapter
from app.core.service_factory import get_trading_service
from app.main import app
from app.models.database.trading import DevStockQuote

pytestmark = [pytest.mark.integration, pytest.mark.journey_integration]

HUB_BASE = "/api/v1/trading"
ORDERS_URL = f"{HUB_BASE}/orders"

# Matches the synthetic adapter's default current_date / scenario.
SYMBOL = "AAPL"
QUOTE_DATE = date(2017, 3, 24)
SCENARIO = "default"


def _seed_synthetic_quote() -> None:
    """Ensure tables exist and a synthetic AAPL quote row is present.

    Seeds via the **synchronous** engine/session (psycopg2) on purpose: it has no
    event-loop coupling, so this stays order-independent in the full suite (the
    shared async engine's asyncpg pool otherwise binds connections to whichever
    event loop touched it first, breaking ``asyncio.run`` reuse across tests). It
    also dogfoods the exact sync path #13 repaired. Idempotent.
    """
    from app.models.database import trading  # noqa: F401  (register metadata)
    from app.models.database.base import Base
    from app.storage.database import get_sync_session, sync_engine

    Base.metadata.create_all(sync_engine)

    with get_sync_session() as db:
        existing = (
            db.execute(
                select(DevStockQuote).where(
                    DevStockQuote.symbol == SYMBOL,
                    DevStockQuote.quote_date == QUOTE_DATE,
                    DevStockQuote.scenario == SCENARIO,
                )
            )
            .scalars()
            .first()
        )
        if existing is None:
            db.add(
                DevStockQuote(
                    symbol=SYMBOL,
                    quote_date=QUOTE_DATE,
                    bid=145.00,
                    ask=145.20,
                    price=145.10,
                    volume=1_000_000,
                    scenario=SCENARIO,
                )
            )
            db.commit()


def test_create_order_with_synthetic_test_adapter() -> None:
    """Order creation must succeed using the DB-backed synthetic `test` adapter.

    This is the keyless default path: no adapter injection, no OpenBB. Symbol
    validation goes through the synchronous-session synthetic adapter, which is
    exactly where #13 raised ``greenlet_spawn``.
    """
    _seed_synthetic_quote()

    with TestClient(app) as client:
        # The container-wired service must be the synthetic (sync-session)
        # adapter for this regression to be meaningful.
        adapter = get_trading_service().quote_adapter
        assert isinstance(adapter, DevDataQuoteAdapter), (
            f"expected synthetic DevDataQuoteAdapter, got {type(adapter).__name__}; "
            "this regression test must exercise the sync-session adapter path"
        )

        resp = client.post(
            ORDERS_URL,
            json={
                "symbol": SYMBOL,
                "order_type": "buy",
                "quantity": 10,
                "price": 145.10,
                "condition": "market",
            },
        )

        # Before the fix this was a 400 whose detail carried the greenlet error.
        assert resp.status_code == 200, (
            f"order creation failed ({resp.status_code}): {resp.text}"
        )
        body = resp.json()
        assert body["success"] is True
        assert body["order"]["symbol"] == SYMBOL
        assert body["order"]["quantity"] == 10
        assert body["order"]["status"] == "pending"
