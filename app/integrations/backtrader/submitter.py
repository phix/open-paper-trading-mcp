"""Submit collected :class:`OrderIntent` records to the Hub as paper orders
(ADR 0003).

This is the *only* component that touches an account, and it does so solely via
the Hub's simulated paper-order endpoint (``POST /orders``) — paper-only by
construction, no brokerage path.

Idempotency (ADR 0003): the Hub's ``OrderCreate`` does not yet carry a
``client_intent_id``, so this submitter owns a **local dedupe ledger** (option 2
in the ADR). Each accepted ``client_intent_id`` is persisted; re-running an
export or retrying a failed batch skips intents already accepted, so no
duplicate Paper trades are created. If/when the Hub honors the key natively, the
ledger becomes a belt-and-suspenders backstop.

Run as a CLI::

    uv run python -m app.integrations.backtrader.submitter intents.json \\
        --hub-url http://localhost:2080 --ledger .stockade/submitted.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.integrations.backtrader.order_intent import OrderIntent

DEFAULT_HUB_URL = "http://localhost:2080"
ORDERS_PATH = "/orders"


def _hub_url() -> str:
    """Resolve the Hub base URL from the environment without touching core config."""
    import os

    return os.environ.get("HUB_API_URL", DEFAULT_HUB_URL).rstrip("/")


class HttpResponse(Protocol):
    """Minimal response shape used by the submitter (httpx-compatible)."""

    status_code: int

    def json(self) -> Any: ...


class HttpClient(Protocol):
    """Minimal HTTP client surface — satisfied by ``httpx.Client``.

    Declared as a Protocol so tests can inject a fake without a running Hub.
    """

    def post(self, url: str, json: Any = ...) -> HttpResponse: ...


class DedupeLedger:
    """Persistent set of ``client_intent_id``s already accepted by the Hub.

    Backed by a JSON file so dedupe survives across separate submitter runs
    (the whole point: re-running an export must not double-submit).
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._ids: set[str] = set()
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._ids = set(data.get("submitted", []))
            except (json.JSONDecodeError, OSError):
                self._ids = set()

    def __contains__(self, client_intent_id: str) -> bool:
        return client_intent_id in self._ids

    def add(self, client_intent_id: str) -> None:
        self._ids.add(client_intent_id)
        self._flush()

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"submitted": sorted(self._ids)}, indent=2)
        )

    def __len__(self) -> int:
        return len(self._ids)


@dataclass
class SubmissionResult:
    """Outcome of a :func:`submit_intents` batch."""

    submitted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed

    def summary(self) -> str:
        return (
            f"submitted={len(self.submitted)} "
            f"skipped(dedup)={len(self.skipped)} "
            f"failed={len(self.failed)}"
        )


def submit_intents(
    intents: list[OrderIntent],
    *,
    client: HttpClient,
    ledger: DedupeLedger,
    hub_url: str | None = None,
) -> SubmissionResult:
    """POST each intent to the Hub's paper-order endpoint, honoring the ledger.

    For every intent:

    * if its ``client_intent_id`` is already in ``ledger``, skip it (dedupe);
    * otherwise map it to the Hub's ``OrderCreate`` body and ``POST /orders``;
    * on a 2xx response, record the id in the ledger so it won't resubmit.

    The HTTP client is injected (any object with a compatible ``post``), so the
    mapping + dedupe logic is fully testable without a running Hub.
    """
    base = (hub_url or _hub_url()).rstrip("/")
    url = f"{base}{ORDERS_PATH}"
    result = SubmissionResult()

    for intent in intents:
        cid = intent.client_intent_id
        if cid in ledger:
            result.skipped.append(cid)
            continue

        payload = intent.to_order_create_payload()
        try:
            response = client.post(url, json=payload)
        except Exception as exc:  # network/transport error - retryable next run
            result.failed.append((cid, f"transport error: {exc}"))
            continue

        if 200 <= response.status_code < 300:
            ledger.add(cid)
            result.submitted.append(cid)
        else:
            detail = _safe_detail(response)
            result.failed.append((cid, f"HTTP {response.status_code}: {detail}"))

    return result


def _safe_detail(response: HttpResponse) -> str:
    try:
        return json.dumps(response.json())
    except Exception:
        return "<unparseable response body>"


def _build_httpx_client(timeout: float) -> HttpClient:
    import httpx

    return httpx.Client(timeout=timeout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.integrations.backtrader.submitter",
        description="Submit a backtrader OrderIntent export to the Hub as paper orders.",
    )
    parser.add_argument("export", help="Path to the intents export JSON file.")
    parser.add_argument(
        "--hub-url",
        default=None,
        help="Hub base URL (default: $HUB_API_URL or http://localhost:2080).",
    )
    parser.add_argument(
        "--ledger",
        default=".stockade/submitted.json",
        help="Path to the local dedupe ledger JSON (default: .stockade/submitted.json).",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="HTTP timeout in seconds."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be submitted without calling the Hub.",
    )
    args = parser.parse_args(argv)

    # Imported here so the CLI works even before backtrader is on the path.
    from app.integrations.backtrader.analyzer import load_intents

    intents = load_intents(args.export)
    ledger = DedupeLedger(args.ledger)

    if args.dry_run:
        pending = [i for i in intents if i.client_intent_id not in ledger]
        for intent in pending:
            print(
                f"WOULD POST {intent.client_intent_id} -> "
                f"{json.dumps(intent.to_order_create_payload())}"
            )
        print(
            f"dry-run: {len(pending)} to submit, "
            f"{len(intents) - len(pending)} already in ledger"
        )
        return 0

    client = _build_httpx_client(args.timeout)
    result = submit_intents(
        intents, client=client, ledger=ledger, hub_url=args.hub_url
    )
    print(result.summary())
    for cid, reason in result.failed:
        print(f"FAILED {cid}: {reason}", file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
