"""The :class:`OrderIntent` contract — the only thing that crosses the
backtrader -> Hub seam (ADR 0003).

An ``OrderIntent`` is a minimal, fork-neutral record emitted on the backtrader
side. It mirrors the Hub's :class:`app.schemas.orders.OrderCreate` so the
submitter is a 1:1 field map, not a translation layer with hidden logic.

Field mapping (OrderIntent -> OrderCreate)::

    symbol            -> symbol            (str, unchanged)
    side              -> order_type        ("buy"|"sell" -> OrderType.BUY|SELL)
    quantity          -> quantity          (int, > 0)
    order_type        -> condition         ("market"|"limit" -> OrderCondition)
    limit_price       -> price             (float | None; None for market)
    client_intent_id  -> client_intent_id  (idempotency key, honored by the Hub)
    strategy          -> (no OrderCreate field; provenance only)

The Hub's ``OrderCreate`` now carries ``client_intent_id`` (ADR 0003 idempotency
option 1): a repeated key returns the existing order instead of a duplicate paper
trade. The submitter's local dedupe ledger remains as a belt-and-suspenders
backstop. The originating ``strategy`` name has no Hub field and is carried only
for provenance/export.

Scope: equities, single-leg only. Options/multi-leg intents are out of scope.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

# Allowed enum-like string values, kept in lock-step with the Hub schema.
_VALID_SIDES = {"buy", "sell"}
_VALID_ORDER_TYPES = {"market", "limit"}

# OrderIntent.side -> Hub OrderType value.
_SIDE_TO_ORDER_TYPE = {"buy": "buy", "sell": "sell"}
# OrderIntent.order_type -> Hub OrderCondition value.
_ORDER_TYPE_TO_CONDITION = {"market": "market", "limit": "limit"}


def make_client_intent_id(
    *,
    strategy: str,
    symbol: str,
    side: str,
    order_type: str,
    quantity: int,
    limit_price: float | None,
    timestamp: str,
    sequence: int = 0,
) -> str:
    """Build a *stable* idempotency key from the intent's identity.

    Per ADR 0003 the key is derived from the intent's identity (strategy +
    symbol + the bar/timestamp that triggered it), **not** a random UUID. The
    same logical order produced on the same bar yields the same id across
    re-runs and retries, which is what lets the dedupe ledger prevent double
    submission.

    ``sequence`` disambiguates multiple orders that share the same identity
    within a single run (e.g. two same-side fills on one bar); it is assigned
    deterministically by the collector, so identical re-runs reproduce the same
    ids.
    """
    basis = "|".join(
        [
            strategy,
            symbol,
            side,
            order_type,
            str(quantity),
            "" if limit_price is None else format(float(limit_price), ".6f"),
            timestamp,
            str(sequence),
        ]
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    # Readable prefix aids debugging/export review; the digest guarantees
    # uniqueness/stability.
    return f"{strategy}:{symbol}:{digest}"


@dataclass(frozen=True)
class OrderIntent:
    """A fork-neutral order intent that maps 1:1 onto the Hub's ``OrderCreate``.

    Frozen so an intent, once emitted, is an immutable record (the ADR's "plain
    data record" that crosses the seam).
    """

    symbol: str
    side: str  # "buy" | "sell"  -> Hub OrderType
    quantity: int  # whole shares, > 0
    order_type: str  # "market" | "limit"  -> Hub OrderCondition
    limit_price: float | None  # required iff order_type == "limit"
    client_intent_id: str  # stable idempotency key
    strategy: str  # originating Strategy name, for provenance

    def __post_init__(self) -> None:
        if self.side not in _VALID_SIDES:
            raise ValueError(
                f"side must be one of {sorted(_VALID_SIDES)}, got {self.side!r}"
            )
        if self.order_type not in _VALID_ORDER_TYPES:
            raise ValueError(
                "order_type must be one of "
                f"{sorted(_VALID_ORDER_TYPES)}, got {self.order_type!r}"
            )
        if not isinstance(self.quantity, int) or self.quantity <= 0:
            raise ValueError(f"quantity must be a positive int, got {self.quantity!r}")
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit_price is required when order_type == 'limit'")
        if self.order_type == "market" and self.limit_price is not None:
            raise ValueError("limit_price must be None when order_type == 'market'")
        if not self.symbol:
            raise ValueError("symbol must be a non-empty string")
        if not self.client_intent_id:
            raise ValueError("client_intent_id must be a non-empty string")

    def to_order_create_payload(self) -> dict[str, Any]:
        """Map this intent to the JSON body for the Hub's ``POST /orders``.

        Returns exactly the fields the Hub's ``OrderCreate`` accepts, including
        ``client_intent_id`` so the Hub can dedupe a repeated submit (ADR 0003
        idempotency option 1). ``strategy`` is omitted (no corresponding Hub
        field; provenance only).
        """
        return {
            "symbol": self.symbol,
            "order_type": _SIDE_TO_ORDER_TYPE[self.side],
            "quantity": self.quantity,
            "price": self.limit_price,
            "condition": _ORDER_TYPE_TO_CONDITION[self.order_type],
            "client_intent_id": self.client_intent_id,
        }

    def to_dict(self) -> dict[str, Any]:
        """Full intent as a JSON-serializable dict (for the export artifact)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrderIntent:
        """Rebuild an intent from its exported dict form."""
        return cls(
            symbol=data["symbol"],
            side=data["side"],
            quantity=int(data["quantity"]),
            order_type=data["order_type"],
            limit_price=(
                None if data.get("limit_price") is None else float(data["limit_price"])
            ),
            client_intent_id=data["client_intent_id"],
            strategy=data["strategy"],
        )
