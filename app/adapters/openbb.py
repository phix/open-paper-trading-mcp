"""OpenBB-backed quote adapter.

Read-only market data sourced from the OpenBB Platform (``from openbb import obb``)
and translated onto the Hub's ``Quote`` model. This is Hub-side glue that *calls into*
OpenBB; OpenBB itself stays untouched (see ADR 0002, issue phix/stockade#7).

Scope is QUOTES first. Options-chain fidelity is explicitly out of scope for this
adapter (ADR 0002): the chain/expiration methods are honest no-ops that return the
same "no data" shape (``None`` / ``[]``) the ``QuoteAdapter`` contract already allows,
so they never crash ``TradingService``.

Design notes:
- ``obb.*`` calls are synchronous; every call is run off the event loop via
  ``asyncio.to_thread`` and bounded by ``AdapterConfig.timeout``.
- A failed or empty OpenBB response yields ``None`` from ``get_quote`` (and an omitted
  key from ``get_quotes``) rather than raising into the caller. Raw OpenBB / provider
  exceptions (rate-limit / auth / timeout) are caught and logged here, never leaked.
- The zero-key default provider is ``yfinance`` so the adapter is usable before any
  provider API keys are configured. Provider keys, when present, are mapped onto
  ``obb.user.credentials`` at first use.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.adapters.base import AdapterConfig, QuoteAdapter
from app.core.logging import logger
from app.models.assets import Asset, Option
from app.models.quotes import OptionsChain, Quote

# Zero-key default provider so the adapter works without any configured API keys.
DEFAULT_PROVIDER = "yfinance"

# Map of OpenBB credential attribute -> environment variable fallback. Applied
# best-effort onto ``obb.user.credentials``; absent keys simply leave the default
# (keyless) provider as the usable path.
_CREDENTIAL_ENV = {
    "fmp_api_key": "OPENBB_FMP_API_KEY",
    "polygon_api_key": "OPENBB_POLYGON_API_KEY",
    "intrinio_api_key": "OPENBB_INTRINIO_API_KEY",
    "tiingo_token": "OPENBB_TIINGO_TOKEN",
    "alpha_vantage_api_key": "OPENBB_ALPHA_VANTAGE_API_KEY",
}

# NYSE regular trading session (local Eastern time).
_NYSE_TZ = ZoneInfo("America/New_York")
_NYSE_OPEN = (9, 30)
_NYSE_CLOSE = (16, 0)


class OpenBBConfig(AdapterConfig):
    """Configuration for the OpenBB quote adapter."""

    name: str = "openbb"
    priority: int = 20
    cache_ttl: float = 300.0  # 5 minutes; live-ish data, blunt rate limits via cache


class OpenBBQuoteAdapter(QuoteAdapter):
    """Quote adapter backed by the OpenBB Platform (equity price quotes)."""

    def __init__(self, config: AdapterConfig | None = None) -> None:
        self.config = config or OpenBBConfig()

        cfg = self.config.config or {}
        self._provider: str = (
            cfg.get("provider") or os.getenv("OPENBB_PROVIDER") or DEFAULT_PROVIDER
        )

        # OpenBB is imported lazily on first use so importing this module (e.g. for
        # the registry) never pays OpenBB's heavy import cost.
        self._obb: Any | None = None
        self._credentials_applied = False
        logger.info(
            "OpenBBQuoteAdapter initialised", extra={"provider": self._provider}
        )

    # ------------------------------------------------------------------ helpers

    def _get_obb(self) -> Any:
        """Lazily import ``obb`` and apply any configured provider credentials."""
        if self._obb is None:
            from openbb import obb  # imported here to keep module import cheap

            self._obb = obb
            self._apply_credentials()
        return self._obb

    def _apply_credentials(self) -> None:
        """Best-effort map of Hub config / env onto ``obb.user.credentials``."""
        if self._credentials_applied or self._obb is None:
            return
        self._credentials_applied = True

        cfg = self.config.config or {}
        creds: dict[str, str] = {}
        for attr, env_var in _CREDENTIAL_ENV.items():
            value = cfg.get(attr) or os.getenv(env_var)
            if value:
                creds[attr] = value

        # A generic AdapterConfig.api_key maps onto the configured provider's slot.
        if self.config.api_key:
            provider_slot = f"{self._provider}_api_key"
            creds.setdefault(provider_slot, self.config.api_key)

        for attr, value in creds.items():
            try:
                setattr(self._obb.user.credentials, attr, value)
            except Exception as exc:  # never fail init over an unknown cred slot
                logger.warning(
                    "OpenBB credential not applied",
                    extra={"attr": attr, "error": str(exc)},
                )

    async def _run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous ``obb`` call off the event loop, bounded by timeout."""
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs), timeout=self.config.timeout
        )

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        if hasattr(row, "model_dump"):
            return row.model_dump()  # type: ignore[no-any-return]
        if isinstance(row, dict):
            return row
        return dict(row)

    def _build_quote(self, asset: Asset, row: Any) -> Quote | None:
        """Translate one OpenBB result row onto the Hub's ``Quote`` model."""
        data = self._row_to_dict(row)

        # Prefer the live last trade; fall back to close / previous close.
        price = data.get("last_price")
        if price is None:
            price = data.get("close")
        if price is None:
            price = data.get("prev_close")

        bid = data.get("bid") or 0.0
        ask = data.get("ask") or 0.0
        volume = data.get("volume")

        try:
            return Quote(
                asset=asset,
                quote_date=datetime.now(UTC),
                price=float(price) if price is not None else None,
                bid=max(float(bid), 0.0),
                ask=max(float(ask), 0.0),
                bid_size=int(data.get("bid_size") or 0),
                ask_size=int(data.get("ask_size") or 0),
                volume=int(volume) if volume is not None else None,
            )
        except Exception as exc:
            logger.warning(
                "OpenBB row could not be mapped to Quote",
                extra={"symbol": getattr(asset, "symbol", None), "error": str(exc)},
            )
            return None

    def _fetch_rows(self, symbol: str) -> list[Any]:
        """Call ``obb.equity.price.quote`` and normalise to a list of rows."""
        obb = self._get_obb()
        response = obb.equity.price.quote(symbol, provider=self._provider)
        results = getattr(response, "results", response)
        if results is None:
            return []
        return results if isinstance(results, list) else [results]

    # -------------------------------------------------------------- quote API

    async def get_quote(self, asset: Asset) -> Quote | None:
        """Get a single quote for an asset (equities only; options out of scope)."""
        if isinstance(asset, Option):
            logger.debug(
                "OpenBB adapter: option quotes out of scope (ADR 0002)",
                extra={"symbol": asset.symbol},
            )
            return None

        try:
            rows = await self._run(self._fetch_rows, asset.symbol)
        except TimeoutError:
            logger.warning(
                "OpenBB quote timed out",
                extra={"symbol": asset.symbol, "timeout": self.config.timeout},
            )
            return None
        except Exception as exc:
            # Provider rate-limit / auth / network errors are absorbed here so they
            # never leak into TradingService as raw OpenBB exceptions.
            logger.warning(
                "OpenBB quote failed",
                extra={
                    "symbol": asset.symbol,
                    "provider": self._provider,
                    "error": str(exc),
                },
            )
            return None

        if not rows:
            return None
        return self._build_quote(asset, rows[0])

    async def get_quotes(self, assets: list[Asset]) -> dict[Asset, Quote]:
        """Get quotes for multiple assets; missing/failed symbols are omitted."""
        results: dict[Asset, Quote] = {}
        for asset in assets:
            quote = await self.get_quote(asset)
            if quote is not None:
                results[asset] = quote
        return results

    # --------------------------------------------------- options (out of scope)

    async def get_chain(
        self, underlying: str, expiration_date: datetime | None = None
    ) -> list[Asset]:
        """Options chain — out of scope for the OpenBB adapter (ADR 0002)."""
        logger.debug(
            "OpenBB adapter: get_chain out of scope (ADR 0002)",
            extra={"underlying": underlying},
        )
        return []

    async def get_options_chain(
        self, underlying: str, expiration_date: datetime | None = None
    ) -> OptionsChain | None:
        """Options chain — out of scope for the OpenBB adapter (ADR 0002)."""
        logger.debug(
            "OpenBB adapter: get_options_chain out of scope (ADR 0002)",
            extra={"underlying": underlying},
        )
        return None

    def get_expiration_dates(self, underlying: str) -> list[date]:
        """Expiration dates — out of scope for the OpenBB adapter (ADR 0002)."""
        return []

    # --------------------------------------------------------- market metadata

    async def is_market_open(self) -> bool:
        """Best-effort NYSE regular-session check (no network call)."""
        now = datetime.now(_NYSE_TZ)
        if now.weekday() >= 5:  # Saturday / Sunday
            return False
        open_t = now.replace(
            hour=_NYSE_OPEN[0], minute=_NYSE_OPEN[1], second=0, microsecond=0
        )
        close_t = now.replace(
            hour=_NYSE_CLOSE[0], minute=_NYSE_CLOSE[1], second=0, microsecond=0
        )
        return open_t <= now <= close_t

    async def get_market_hours(self) -> dict[str, Any]:
        """Return best-effort NYSE regular-session hours for the current day."""
        now = datetime.now(_NYSE_TZ)
        is_open = await self.is_market_open()
        return {
            "is_open": is_open,
            "timezone": "America/New_York",
            "regular_open": "09:30",
            "regular_close": "16:00",
            "date": now.date().isoformat(),
            "source": "openbb-adapter-heuristic",
        }

    # ------------------------------------------------------- adapter metadata

    def get_sample_data_info(self) -> dict[str, Any]:
        return {
            "message": "OpenBBQuoteAdapter serves live OpenBB data, not sample data",
            "provider": self._provider,
        }

    def get_test_scenarios(self) -> dict[str, Any]:
        return {"message": "OpenBBQuoteAdapter uses live data, no test scenarios"}

    def set_date(self, date: str) -> None:
        """No-op: OpenBB serves live data, there is no settable test date."""
        return None

    def get_available_symbols(self) -> list[str]:
        """Provider-dependent and unbounded; not enumerated here."""
        return []
