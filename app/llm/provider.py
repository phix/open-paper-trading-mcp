"""Swappable LLM provider seam for the Hub's agent/inference layer.

ADR 0004 (phix/stockade#6) repoints the Hub's agent from a hard Gemini/ADK
wiring to a *seam*: the inference backend is chosen by configuration, not by a
code change. Two interchangeable providers live behind this seam:

* ``local``  — the self-hosted LLM ``tinman`` (``qwen2.5-coder-7b-instruct``
  served by LM Studio, which speaks the OpenAI API) reached over Tailscale at
  ``LLM_BASE_URL`` (default ``http://tinman:1234/v1``). Selecting this provider
  returns an OpenAI-compatible client pointed at that base URL.
* ``gemini`` — the existing Google Gemini/ADK path. The ADK example agent reads
  ``GOOGLE_MODEL`` / ``GOOGLE_API_KEY`` directly; this seam only resolves which
  model the Gemini path should use and leaves ADK to build its own ``Agent``.

This is the seam only — not a full agent rewrite. Callers ask for a
``ResolvedProvider`` and target whichever backend ``LLM_PROVIDER`` names.

Operator note (ADR 0004): when ``LLM_PROVIDER=local`` the Tailscale VPN is a
runtime dependency. With the VPN down, ``LLM_BASE_URL`` is unreachable and the
local provider's client calls will fail at request time (construction does not
reach the network). Fall back to ``LLM_PROVIDER=gemini`` if the VPN is down.

Paper-only: no order-routing or brokerage code lives here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from app.core.config import Settings, settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from openai import OpenAI

# Fallback Gemini model, matching examples/google_adk_agent/agent.py, used when
# GOOGLE_MODEL is unset so the seam never returns an empty model name.
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


class LLMProvider(StrEnum):
    """The inference backends selectable behind the seam."""

    LOCAL = "local"
    GEMINI = "gemini"


@dataclass(frozen=True)
class ResolvedProvider:
    """The outcome of selecting a provider from configuration.

    Attributes:
        provider: Which backend was selected.
        model: The model name the selected backend should use.
        base_url: OpenAI-compatible endpoint for ``local``; ``None`` for
            ``gemini`` (ADK manages its own transport).
        client: An OpenAI-compatible client for ``local``; ``None`` for
            ``gemini`` (the ADK path constructs its own ``Agent``).
    """

    provider: LLMProvider
    model: str
    base_url: str | None
    client: Any | None


def _resolve_provider_name(raw: str) -> LLMProvider:
    """Parse ``LLM_PROVIDER`` case-insensitively into a known provider."""
    try:
        return LLMProvider(raw.strip().lower())
    except ValueError as exc:  # pragma: no cover - defensive
        valid = ", ".join(p.value for p in LLMProvider)
        raise ValueError(
            f"Unknown LLM_PROVIDER {raw!r}; expected one of: {valid}"
        ) from exc


def _build_local_client(config: Settings) -> OpenAI:
    """Build an OpenAI-compatible client pointed at the local LLM.

    Imported lazily so the ``gemini`` path does not require the ``openai``
    package, and so importing this module is cheap. Constructing the client
    does NOT reach the network; only request calls do.
    """
    from openai import OpenAI

    return OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)


def get_llm_provider(config: Settings | None = None) -> ResolvedProvider:
    """Select and resolve the LLM provider from configuration.

    Args:
        config: Settings to read from; defaults to the process-wide
            ``settings`` singleton. Injectable for tests.

    Returns:
        A ``ResolvedProvider`` describing the chosen backend. For ``local``,
        ``client`` is a ready OpenAI-compatible client targeting
        ``LLM_BASE_URL``. For ``gemini``, ``client``/``base_url`` are ``None``
        and ``model`` resolves from ``GOOGLE_MODEL``.

    Raises:
        ValueError: If ``LLM_PROVIDER`` is not a known provider.
    """
    config = config or settings
    provider = _resolve_provider_name(config.LLM_PROVIDER)

    if provider is LLMProvider.LOCAL:
        return ResolvedProvider(
            provider=provider,
            model=config.LLM_MODEL,
            base_url=config.LLM_BASE_URL,
            client=_build_local_client(config),
        )

    # gemini: the ADK example agent reads GOOGLE_MODEL / GOOGLE_API_KEY itself;
    # the seam only resolves which model that path should use.
    return ResolvedProvider(
        provider=provider,
        model=os.getenv("GOOGLE_MODEL") or DEFAULT_GEMINI_MODEL,
        base_url=None,
        client=None,
    )
