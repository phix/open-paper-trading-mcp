"""Unit tests for the LLM provider seam (ADR 0004 / phix/stockade#6).

These tests exercise provider *selection* only. They mock the network and do
NOT reach the live tinman endpoint (which is VPN-only and unreachable from CI):
constructing an OpenAI client does no network I/O, and the Gemini path returns
no client at all.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.llm.provider import (
    DEFAULT_GEMINI_MODEL,
    LLMProvider,
    get_llm_provider,
)

pytestmark = pytest.mark.unit

TINMAN_BASE_URL = "http://tinman:1234/v1"


def _settings(**overrides: str) -> Settings:
    """Build a Settings instance with LLM overrides, ignoring the real .env."""
    base = {
        "LLM_PROVIDER": "gemini",
        "LLM_BASE_URL": TINMAN_BASE_URL,
        "LLM_API_KEY": "lm-studio",
        "LLM_MODEL": "qwen2.5-coder-7b-instruct",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_local_provider_returns_client_pointed_at_tinman() -> None:
    resolved = get_llm_provider(_settings(LLM_PROVIDER="local"))

    assert resolved.provider is LLMProvider.LOCAL
    assert resolved.model == "qwen2.5-coder-7b-instruct"
    assert resolved.base_url == TINMAN_BASE_URL
    assert resolved.client is not None
    # The OpenAI client is configured with the tinman base_url (no network I/O).
    assert str(resolved.client.base_url).rstrip("/") == TINMAN_BASE_URL


def test_local_provider_is_case_insensitive() -> None:
    resolved = get_llm_provider(_settings(LLM_PROVIDER="LOCAL"))

    assert resolved.provider is LLMProvider.LOCAL
    assert resolved.base_url == TINMAN_BASE_URL


def test_gemini_provider_returns_adk_path_without_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_MODEL", "gemini-1.5-flash")

    resolved = get_llm_provider(_settings(LLM_PROVIDER="gemini"))

    assert resolved.provider is LLMProvider.GEMINI
    # Gemini is the ADK path: no OpenAI client, no OpenAI-compatible base_url.
    assert resolved.client is None
    assert resolved.base_url is None
    assert resolved.model == "gemini-1.5-flash"


def test_gemini_provider_falls_back_to_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_MODEL", raising=False)

    resolved = get_llm_provider(_settings(LLM_PROVIDER="gemini"))

    assert resolved.model == DEFAULT_GEMINI_MODEL


def test_default_provider_is_gemini() -> None:
    # Safe default: existing Gemini behavior is unchanged until the local swap
    # is verified (ADR 0004 / issue #6 acceptance criteria).
    resolved = get_llm_provider(_settings())

    assert resolved.provider is LLMProvider.GEMINI


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_llm_provider(_settings(LLM_PROVIDER="bedrock"))
