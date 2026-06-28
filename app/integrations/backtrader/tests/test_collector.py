"""Integration test for the OrderIntentCollector Analyzer (ADR 0003).

Runs a tiny backtrader backtest and asserts the analyzer captured order intents.
Skipped automatically when ``backtrader`` is not importable (it lives in the
sibling fork and is not a Hub dependency); put the fork on ``PYTHONPATH`` to run
it, e.g. ``PYTHONPATH=/path/to/stockade/backtrader uv run pytest ...``.
"""

from __future__ import annotations

import datetime

import pytest

bt = pytest.importorskip("backtrader")

from app.integrations.backtrader.analyzer import (  # noqa: E402
    get_collector_class,
    load_intents,
)
from app.integrations.backtrader.order_intent import OrderIntent  # noqa: E402


class _BuyThenSell(bt.Strategy):
    """Buys on bar 1, sells on bar 3 — deterministic, no indicators."""

    def __init__(self) -> None:
        self._bar = 0

    def next(self) -> None:
        self._bar += 1
        if self._bar == 1:
            self.buy(size=10)
        elif self._bar == 3:
            self.sell(size=10)


def _feed() -> bt.feeds.PandasData:
    pd = pytest.importorskip("pandas")
    days = [datetime.datetime(2024, 1, d) for d in range(1, 6)]
    df = pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104],
            "high": [101, 102, 103, 104, 105],
            "low": [99, 100, 101, 102, 103],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "volume": [1000] * 5,
        },
        index=pd.DatetimeIndex(days),
    )
    return bt.feeds.PandasData(dataname=df)


def _run() -> object:
    cerebro = bt.Cerebro()
    cerebro.addstrategy(_BuyThenSell)
    data = _feed()
    data._name = "AAPL"
    cerebro.adddata(data)
    cerebro.addanalyzer(
        get_collector_class(), _name="order_intents", strategy_name="BuyThenSell"
    )
    return cerebro.run()[0]


def test_collector_records_one_intent_per_order():
    strat = _run()
    intents = strat.analyzers.order_intents.intents()
    assert len(intents) == 2
    assert all(isinstance(i, OrderIntent) for i in intents)

    buy, sell = intents
    assert buy.side == "buy"
    assert buy.symbol == "AAPL"
    assert buy.quantity == 10
    assert buy.order_type == "market"
    assert buy.strategy == "BuyThenSell"
    assert sell.side == "sell"

    # Each intent maps cleanly to an OrderCreate payload.
    assert buy.to_order_create_payload()["order_type"] == "buy"
    assert sell.to_order_create_payload()["order_type"] == "sell"


def test_collector_ids_are_stable_across_reruns():
    ids_1 = [i.client_intent_id for i in _run().analyzers.order_intents.intents()]
    ids_2 = [i.client_intent_id for i in _run().analyzers.order_intents.intents()]
    assert ids_1 == ids_2  # same export keys on re-run -> dedupe works


def test_export_and_reload_round_trip(tmp_path):
    strat = _run()
    out = strat.analyzers.order_intents.export(tmp_path / "intents.json")
    reloaded = load_intents(out)
    # Export is keyed by client_intent_id, so order is not significant.
    assert {i.client_intent_id for i in reloaded} == {
        i.client_intent_id for i in strat.analyzers.order_intents.intents()
    }
    assert len(reloaded) == 2
