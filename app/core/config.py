import logging
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )

    PROJECT_NAME: str = "Open Paper Trading MCP"
    API_V1_STR: str = "/api/v1"

    # CORS - simplified for Docker
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://localhost:2080"

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://trading_user:trading_password@db:5432/trading_db",
    )

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Security
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "your-secret-key-change-this-in-production"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # MCP Server Configuration
    MCP_SERVER_PORT: int = int(os.getenv("MCP_SERVER_PORT", "2081"))
    MCP_SERVER_HOST: str = os.getenv("MCP_SERVER_HOST", "localhost")
    MCP_SERVER_NAME: str = "Open Paper Trading MCP"
    MCP_HTTP_PORT: int = int(os.getenv("MCP_HTTP_PORT", "2081"))
    MCP_HTTP_URL: str = os.getenv("MCP_HTTP_URL", "http://localhost:2081")

    # Quote Adapter Configuration
    QUOTE_ADAPTER_TYPE: str = os.getenv("QUOTE_ADAPTER_TYPE", "test")

    # Test Data Configuration
    TEST_SCENARIO: str = os.getenv("TEST_SCENARIO", "ui_testing")
    TEST_DATE: str = os.getenv("TEST_DATE", "2025-07-30")

    # Robinhood Configuration
    ROBINHOOD_USERNAME: str = os.getenv("ROBINHOOD_USERNAME", "")
    ROBINHOOD_PASSWORD: str = os.getenv("ROBINHOOD_PASSWORD", "")
    ROBINHOOD_TOKEN_PATH: str = os.getenv("ROBINHOOD_TOKEN_PATH", "/app/.tokens")

    # LLM provider seam (ADR 0004 / phix/stockade#6)
    # Selects the agent's inference backend behind a swappable seam:
    #   gemini -> existing Google Gemini/ADK path (GOOGLE_MODEL / GOOGLE_API_KEY)
    #   local  -> self-hosted LLM (tinman, LM Studio, OpenAI-compatible)
    # Default stays `gemini` so existing behavior is unchanged until the local
    # swap is verified. The LLM_* vars below drive the `local` provider.
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")  # local | gemini
    # Use the Tailscale MagicDNS name (not bare "tinman", which also resolves to
    # dead public IPv6 addresses). Verified reachable; LM Studio serving qwen2.5.
    LLM_BASE_URL: str = os.getenv(
        "LLM_BASE_URL", "http://tinman.tailc095b7.ts.net:1234/v1"
    )
    # Non-secret placeholder; LM Studio ignores the key but the client requires one.
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "lm-studio")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen2.5-coder-7b-instruct")

    # Agent run guard (phix/stockade#25)
    # Hard cap on the number of LLM calls a single ADK agent invocation may make,
    # passed as RunConfig(max_llm_calls=...) wherever WE run the agent under our
    # control (see examples/google_adk_agent/runner.py). ADK's own default is 500,
    # which let runaway tool-call loops (observed: `option_credit_spread`) burn to
    # "Max llm calls (500) exceeded" before failing. A low cap (30) makes such
    # loops fail fast. NOTE: the `adk eval` CLI path does NOT consume this — it
    # builds its own Runner and calls run_async without a run_config, so it stays
    # pinned to ADK's 500 default with no override knob.
    AGENT_MAX_LLM_CALLS: int = int(os.getenv("AGENT_MAX_LLM_CALLS", "30"))

    def get_cors_origins(self) -> list[str]:
        """Convert CORS origins string to list."""
        if isinstance(self.BACKEND_CORS_ORIGINS, str):
            return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",")]
        return self.BACKEND_CORS_ORIGINS


settings = Settings()
