"""A backtrader Analyzer that collects :class:`OrderIntent` records as a
strategy trades, for offline export (ADR 0003).

This stays **outside** the submit path: it only *observes* the backtrader order
stream during a run and converts each placed order into a fork-neutral
``OrderIntent``. The Strategy itself trades with the normal ``self.buy()`` /
``self.sell()`` calls and never imports the Hub. Submission is a separate,
explicit step (:func:`app.integrations.backtrader.submitter.submit_intents`).

``backtrader`` is imported lazily inside :func:`get_collector_class` so the rest
of the package (the intent contract + submitter) stays importable in the Hub's
environment, which does not depend on backtrader.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.integrations.backtrader.order_intent import (
    OrderIntent,
    make_client_intent_id,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


# backtrader exectype -> OrderIntent.order_type. Only equity market/limit are in
# scope (ADR 0003); other exec types are skipped (with a recorded reason).
_EXECTYPE_TO_ORDER_TYPE = {
    "Market": "market",
    "Limit": "limit",
}


def _build_collector_class(bt: Any) -> type:
    """Construct the Analyzer subclass bound to the given ``backtrader`` module.

    Defined as a factory so importing this module never requires backtrader.
    """

    class OrderIntentCollector(bt.Analyzer):  # type: ignore[misc, name-defined]
        """Collects emitted order intents during a backtrader run.

        Hooks ``notify_order``; on the first notification of each order
        (``Submitted``) it derives a stable ``client_intent_id`` and records an
        :class:`OrderIntent`. Skipped orders (unsupported exec type, non-equity)
        are tracked separately so nothing is silently dropped.

        Access results after ``cerebro.run()`` via ``get_analysis()`` (an
        OrderedDict keyed by ``client_intent_id``) or export them with
        :meth:`export`.
        """

        params = (("strategy_name", None),)

        def start(self) -> None:
            self._intents: OrderedDict[str, OrderIntent] = OrderedDict()
            self._skipped: list[dict[str, Any]] = []
            self._seen_ref: set[int] = set()
            # Deterministic per-identity sequence counter for id disambiguation.
            self._seq: dict[tuple, int] = {}

        def _strategy_name(self) -> str:
            name = self.p.strategy_name
            if name:
                return str(name)
            return type(self.strategy).__name__

        def notify_order(self, order: Any) -> None:
            # Record each order exactly once, at submission time. Later
            # status transitions (Accepted/Completed) re-notify the same ref.
            if order.ref in self._seen_ref:
                return
            if order.status != order.Submitted:
                return
            self._seen_ref.add(order.ref)

            exectype_name = bt.Order.ExecTypes[order.exectype]
            order_type = _EXECTYPE_TO_ORDER_TYPE.get(exectype_name)
            symbol = getattr(order.data, "_name", "") or ""

            side = "buy" if order.isbuy() else "sell"
            quantity = abs(int(order.size)) if order.size is not None else 0

            if order_type is None or not symbol or quantity <= 0:
                self._skipped.append(
                    {
                        "ref": order.ref,
                        "symbol": symbol,
                        "exectype": exectype_name,
                        "size": order.size,
                        "reason": "unsupported-exectype-or-missing-fields",
                    }
                )
                return

            limit_price: float | None = None
            if order_type == "limit":
                price = order.created.price if order.created.price else order.price
                limit_price = None if price is None else float(price)

            try:
                timestamp = bt.num2date(order.data.datetime[0]).isoformat()
            except (IndexError, ValueError):
                timestamp = ""

            strategy_name = self._strategy_name()
            identity = (strategy_name, symbol, side, order_type, quantity, limit_price,
                        timestamp)
            sequence = self._seq.get(identity, 0)
            self._seq[identity] = sequence + 1

            client_intent_id = make_client_intent_id(
                strategy=strategy_name,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                limit_price=limit_price,
                timestamp=timestamp,
                sequence=sequence,
            )

            intent = OrderIntent(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
                client_intent_id=client_intent_id,
                strategy=strategy_name,
            )
            self._intents[client_intent_id] = intent

        def get_analysis(self) -> OrderedDict:
            return self._intents

        def intents(self) -> list[OrderIntent]:
            return list(self._intents.values())

        def skipped(self) -> list[dict[str, Any]]:
            return list(self._skipped)

        def export(self, path: str | Path) -> Path:
            """Write the collected intents to a JSON export artifact.

            Shape: ``{"intents": {<client_intent_id>: <intent dict>, ...}}`` —
            keyed by ``client_intent_id`` so the export is itself idempotent and
            reviewable before submission.
            """
            out = Path(path)
            payload = {
                "intents": {
                    cid: intent.to_dict() for cid, intent in self._intents.items()
                }
            }
            out.write_text(json.dumps(payload, indent=2, sort_keys=True))
            return out

    return OrderIntentCollector


_COLLECTOR_CLASS: type | None = None


def get_collector_class() -> type:
    """Return the ``OrderIntentCollector`` Analyzer class (imports backtrader).

    Call this where backtrader is available (the backtrader fork's env)::

        import backtrader as bt
        from app.integrations.backtrader.analyzer import get_collector_class

        cerebro.addanalyzer(get_collector_class(), _name="order_intents")
        strat = cerebro.run()[0]
        strat.analyzers.order_intents.export("intents.json")
    """
    global _COLLECTOR_CLASS
    if _COLLECTOR_CLASS is None:
        import backtrader as bt

        _COLLECTOR_CLASS = _build_collector_class(bt)
    return _COLLECTOR_CLASS


def load_intents(path: str | Path) -> list[OrderIntent]:
    """Read an export artifact back into a list of :class:`OrderIntent`."""
    data = json.loads(Path(path).read_text())
    intents = data.get("intents", {})
    return [OrderIntent.from_dict(d) for d in intents.values()]
