"""backtrader -> Hub paper-execution seam (ADR 0003).

Offline export -> submit, NOT an in-loop broker. A backtrader Strategy trades
normally; an :class:`OrderIntentCollector` Analyzer records each order as a
fork-neutral :class:`OrderIntent`; a separate :func:`submit_intents` step POSTs
those intents to the Hub's paper-order API (``POST /orders``) with a local
dedupe ledger keyed on ``client_intent_id`` so re-running never double-submits.

Paper-only by construction: the only thing that places an order is a Hub paper
call. There is no brokerage path here.

The Analyzer (``analyzer`` submodule) imports ``backtrader`` lazily so that the
intent contract and submitter remain importable in the Hub's environment, which
does not depend on backtrader.
"""

from app.integrations.backtrader.order_intent import (
    OrderIntent,
    make_client_intent_id,
)
from app.integrations.backtrader.submitter import (
    DedupeLedger,
    SubmissionResult,
    submit_intents,
)

__all__ = [
    "DedupeLedger",
    "OrderIntent",
    "SubmissionResult",
    "make_client_intent_id",
    "submit_intents",
]
