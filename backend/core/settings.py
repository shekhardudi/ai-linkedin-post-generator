"""Centralised application settings — single source of truth for env config.

Every model identifier, tunable LLM parameter, and rate limit lives here.
Override any of them with environment variables (or `.env`) — no code change
required. The previous design scattered `os.getenv()` and string literals
across modules; this consolidates them.
"""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import repo_root

# Load .env into os.environ so anything still calling os.getenv() picks up the
# same values pydantic-settings reads (crewAI/LiteLLM look up provider keys
# via os.environ, for instance).
load_dotenv(repo_root() / ".env", override=False)


class Settings(BaseSettings):
    """Reads .env at the repo root. Override with real environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(repo_root() / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Required keys
    # ------------------------------------------------------------------
    openai_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    tavily_api_key: str = Field(default="")
    serper_api_key: str = Field(default="")

    # ------------------------------------------------------------------
    # Models — every LLM call routes through one of these strings.
    # Crew/LiteLLM identifiers use "<provider>/<model-id>" form;
    # SDK-direct identifiers (Anthropic, OpenAI image) are bare ids.
    # ------------------------------------------------------------------
    crew_researcher_model: str = "openai/gpt-5"
    crew_writer_model: str = "anthropic/claude-opus-4-7"
    crew_critic_model: str = "anthropic/claude-sonnet-4-6"

    # Visual Director uses the Anthropic SDK directly. Stored with the
    # "anthropic/" prefix for pricing-table lookups; we strip it before
    # passing to the SDK.
    visual_director_model: str = "anthropic/claude-sonnet-4-6"
    visual_director_temperature: float = 0.7
    visual_director_max_tokens: int = 900

    image_model: str = "gpt-image-1"
    image_default_size: str = "1024x1024"   # 1024x1024 | 1024x1536 | 1536x1024
    image_default_quality: str = "medium"   # low | medium | high

    # ------------------------------------------------------------------
    # Scout config
    # ------------------------------------------------------------------
    scout_use_openai: bool = True
    scout_openai_model: str = "gpt-4o-mini"
    scout_synthesis_temperature: float = 0.7
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    ollama_num_ctx: int = 8192

    # ------------------------------------------------------------------
    # API config
    # ------------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: str = "*"  # comma-separated; "*" means open
    log_pretty: bool = False
    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # Rate limits — slowapi notation ("N/period"). Read at decoration
    # time, so a restart picks up env changes.
    # ------------------------------------------------------------------
    rate_limit_posts: str = "5/minute"
    rate_limit_images: str = "10/minute"

    # ------------------------------------------------------------------
    # Job runner
    # ------------------------------------------------------------------
    max_concurrent_post_jobs: int = 2

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def outputs_path(self) -> Path:
        return repo_root() / "outputs"

    def cors_origins_list(self) -> list[str]:
        if self.api_cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    def crew_models(self) -> list[str]:
        """Ordered list used for proportional cost attribution."""
        return [self.crew_researcher_model, self.crew_writer_model, self.crew_critic_model]

    def model_card(self) -> dict[str, str]:
        """Flat snapshot used for the run history manifest."""
        return {
            "researcher": self.crew_researcher_model,
            "writer": self.crew_writer_model,
            "critic": self.crew_critic_model,
            "visual_director": self.visual_director_model,
            "image": self.image_model,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
