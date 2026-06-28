"""LLM provider seam for the Hub's agent/inference layer.

See ``app.llm.provider`` for the swappable provider abstraction described by
ADR 0004 (phix/stockade#6). Paper-only: no order-routing or brokerage code
lives here.
"""

from app.llm.provider import (
    LLMProvider,
    ResolvedProvider,
    get_llm_provider,
)

__all__ = [
    "LLMProvider",
    "ResolvedProvider",
    "get_llm_provider",
]
