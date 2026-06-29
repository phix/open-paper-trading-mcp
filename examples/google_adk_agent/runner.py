"""Run the Paper Trading agent with a hard cap on LLM calls (phix/stockade#25).

ADK's ``RunConfig.max_llm_calls`` defaults to **500**. On complex, multi-step
workflows the agent can loop on tool calls until it hits that ceiling and dies
with ``Max llm calls (500) exceeded`` (observed live on ``option_credit_spread``).
That is a slow, expensive way to fail. This module is the one place WE run the
agent under our own control, so it pins ``max_llm_calls`` to a sane low cap
(``settings.AGENT_MAX_LLM_CALLS``, default 30) so runaway loops fail fast.

Why this is a runner helper and not an edit to the eval path
------------------------------------------------------------
Today the agent (``agent.root_agent``) is executed in this repo **only** by the
``adk eval`` CLI. That path builds its own ``Runner`` inside ADK's
``EvaluationGenerator`` and calls ``run_async(...)`` **without** a ``run_config``
(see ``google/adk/evaluation/evaluation_generator.py``), so it always falls back
to ``RunConfig()`` with ``max_llm_calls=500``. Neither the ``adk eval`` CLI nor
the eval config file (``tests/evals/test_config.json``, which only carries
``criteria``) exposes a knob to override it. Capping the eval path would mean
monkeypatching the framework, which we will not do.

So the guard lives here: ``run_agent`` is the supported entry point for any
app-side (non-eval) invocation of the agent, and it always applies the cap. When
app code grows a real agent runner, it should call this instead of building a
bare ``Runner``.

ADK imports are top-level here because this module only ever runs in the agent's
own environment (``examples/google_adk_agent/requirements.txt``), where
``google-adk`` is installed — unlike the Hub app env, which has no ADK.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from google.adk.agents.run_config import RunConfig
from google.adk.events.event import Event
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.core.config import settings

from .agent import root_agent

#: App name used for the in-memory session when running the agent standalone.
APP_NAME = "stockade_paper_trading_agent"


def build_run_config(max_llm_calls: int | None = None) -> RunConfig:
    """Build a ``RunConfig`` that caps the agent's LLM calls.

    Args:
        max_llm_calls: Hard cap to apply. Defaults to
            ``settings.AGENT_MAX_LLM_CALLS`` (env ``AGENT_MAX_LLM_CALLS``,
            default 30) when ``None``.

    Returns:
        A ``RunConfig`` carrying the resolved ``max_llm_calls`` so a single
        agent invocation fails fast instead of looping to ADK's 500 default.
    """
    cap = settings.AGENT_MAX_LLM_CALLS if max_llm_calls is None else max_llm_calls
    return RunConfig(max_llm_calls=cap)


async def run_agent(
    message: str,
    *,
    user_id: str = "stockade",
    session_id: str = "default",
    max_llm_calls: int | None = None,
) -> AsyncIterator[Event]:
    """Run the Paper Trading agent for one message with the LLM-call cap applied.

    This is the supported, capped entry point for app-side (non-eval) agent
    invocations. It spins up an ``InMemoryRunner`` over ``root_agent`` and passes
    ``build_run_config()`` so the run cannot exceed ``AGENT_MAX_LLM_CALLS``.

    Args:
        message: The user message to send to the agent.
        user_id: Session user id (in-memory; arbitrary for a single user).
        session_id: Session id to create/reuse for the in-memory session.
        max_llm_calls: Optional override for the per-run LLM-call cap.

    Yields:
        The ``Event`` objects produced by the agent run, in order.
    """
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    await runner.session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    new_message = types.Content(role="user", parts=[types.Part(text=message)])
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
        run_config=build_run_config(max_llm_calls),
    ):
        yield event
