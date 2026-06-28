"""Paper Trading Agent Configuration.

This module configures Paper_Trading_Agent, a specialized agent for handling
paper trading operations through our MCP server.

It uses the specified Google model and connects to our open-paper-trading-mcp server
to provide simulated trading capabilities.
"""

import logging
import os
import warnings

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StreamableHTTPConnectionParams,
)

from app.llm.provider import LLMProvider, get_agent_model_spec

from .prompts import agent_instruction

# Initialize environment and logging
# Load .env from project root (two levels up from this file)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
dotenv_path = os.path.join(project_root, ".env")
load_dotenv(dotenv_path)
logging.basicConfig(level=logging.ERROR)
warnings.filterwarnings("ignore")


def _build_model() -> object:
    """Resolve the agent's model from the Hub's LLM provider seam (ADR 0004).

    Selection is configuration, not code: ``LLM_PROVIDER`` picks the backend.
    ``local`` routes the agent at the self-hosted LM Studio endpoint on ``tinman``
    via ADK's ``LiteLlm`` (LM Studio is OpenAI-compatible); ``gemini`` returns the
    model-name string ADK builds its own Gemini model from. Either way the tools,
    instruction, and MCP transport below are identical.

    ``LiteLlm`` is imported lazily so the Gemini path needs no ``litellm`` install.
    """
    spec = get_agent_model_spec()
    if spec.provider is LLMProvider.LOCAL:
        from google.adk.models.lite_llm import LiteLlm

        return LiteLlm(**spec.litellm_kwargs)
    return spec.gemini_model


def create_agent() -> Agent:
    """
    Creates and returns a configured Paper Trading agent instance.

    Returns:
        Agent: Configured Paper Trading agent with HTTP transport to MCP server.
    """

    # Use HTTP transport - server must be running separately
    http_url = os.environ.get("MCP_HTTP_URL", "http://localhost:2081/mcp")
    agent_tools = [
        MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=http_url,
            ),
        ),
    ]

    return Agent(
        model=_build_model(),
        name="Paper_Trading_Agent",
        instruction=agent_instruction,
        description="Specialized paper trading agent that can perform simulated trading operations through MCP tools.",
        tools=agent_tools,
    )


# Configure specialized Paper Trading operations agent
root_agent = create_agent()
