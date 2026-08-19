from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, ConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Provider registry for engine implementations
PROVIDERS = {
    "mock": "aeo_eval.engine.mock_engine:MockEngine",
    "random-mock": "aeo_eval.engine.mock_engine:RandomMockEngine",
    "claude": "aeo_eval.engine.claude_engine:ClaudeEngine",
    "openai": "aeo_eval.engine.openai_engine:OpenAIEngine",
}


class RetryPolicyConfig(BaseModel):
    """Configuration for retry behavior."""
    max_retries: int = Field(default=3, ge=1, le=10, description="Maximum retry attempts")
    initial_delay_ms: int = Field(default=100, ge=10, description="Initial delay in milliseconds")
    backoff_factor: float = Field(default=2.0, ge=1.0, le=5.0, description="Exponential backoff factor")
    max_delay_ms: int = Field(default=30000, ge=1000, description="Maximum delay cap in milliseconds")


class ProviderConfig(BaseModel):
    """Configuration for a specific AI provider."""
    api_key: Optional[str] = Field(default=None, description="API key (from env var preferred)")
    model_name: str = Field(default="claude-opus-5", description="Model name to use")
    rate_limit_tpm: int = Field(default=150000, ge=1000, description="Tokens per minute limit")
    rate_limit_rpm: int = Field(default=100, ge=10, description="Requests per minute limit")
    timeout_seconds: int = Field(default=60, ge=10, description="Request timeout in seconds")
    cost_per_1k_input_tokens: float = Field(default=0.003, ge=0, description="Cost per 1k input tokens")
    cost_per_1k_output_tokens: float = Field(default=0.015, ge=0, description="Cost per 1k output tokens")
    max_retries: Optional[int] = Field(default=None, description="Override global retry policy")


class GeneralConfig(BaseModel):
    """General system configuration."""
    cost_limit_per_run: float = Field(default=35.0, gt=0, description="Maximum spend per evaluation run ($)")
    question_json_path: Path = Field(default=PROJECT_ROOT / "question.json", description="Path to buyer questions")
    output_db_path: Path = Field(default=PROJECT_ROOT / "data" / "eval_runs.db", description="SQLite database path")
    log_level: str = Field(default="INFO", description="Logging level")


class EvaluationConfig(BaseModel):
    """Configuration for evaluation parameters."""
    competitors: List[str] = Field(
        default=["Fivetran", "Oracle GoldenGate", "Qlik Replicate", "Confluent", "AWS DMS", "Estuary"],
        description="Competitor names to track"
    )
    important_striim_pages: List[str] = Field(
        default=[
            "https://www.striim.com/product/",
            "https://www.striim.com/solutions/",
            "https://www.striim.com/docs/",
        ],
        description="Important Striim URLs to monitor"
    )
    crawlers: List[str] = Field(
        default=[
            "OAI-SearchBot",
            "PerplexityBot",
            "Claude-SearchBot",
            "Googlebot",
            "Bingbot",
        ],
        description="AI crawler user agents to monitor"
    )
    enabled_topics: Optional[List[str]] = Field(default=None, description="Filter to specific topics (optional)")
    enabled_personas: Optional[List[str]] = Field(default=None, description="Filter to specific personas (optional)")


class SchedulingConfig(BaseModel):
    """Configuration for scheduled runs."""
    timezone: str = Field(default="US/Eastern", description="Timezone for scheduling")
    default_schedule: str = Field(default="0 9 * * MON", description="Default cron expression (9am Monday)")


class Config(BaseModel):
    """Root configuration object."""
    model_config = ConfigDict(extra="allow")  # Allow future config sections

    providers: Dict[str, ProviderConfig] = Field(
        default_factory=lambda: {
            "claude": ProviderConfig(
                model_name="claude-opus-5",
                rate_limit_tpm=150000,
                rate_limit_rpm=100,
            ),
            "openai": ProviderConfig(
                model_name="gpt-4o",
                rate_limit_tpm=200000,
                rate_limit_rpm=500,
                cost_per_1k_input_tokens=0.015,
                cost_per_1k_output_tokens=0.060,
            ),
            "gemini": ProviderConfig(
                model_name="gemini-2.0-flash",
                rate_limit_tpm=1000000,
                rate_limit_rpm=1000,
                cost_per_1k_input_tokens=0.075,
                cost_per_1k_output_tokens=0.30,
            ),
            "grok": ProviderConfig(
                model_name="grok-2",
                rate_limit_tpm=200000,
                rate_limit_rpm=100,
                cost_per_1k_input_tokens=0.002,
                cost_per_1k_output_tokens=0.010,
            ),
            "perplexity": ProviderConfig(
                model_name="sonar-pro",
                rate_limit_tpm=150000,
                rate_limit_rpm=100,
                cost_per_1k_input_tokens=0.003,
                cost_per_1k_output_tokens=0.015,
            ),
        },
        description="Provider-specific configurations"
    )
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig, description="Retry behavior")
    general: GeneralConfig = Field(default_factory=GeneralConfig, description="General settings")
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig, description="Evaluation parameters")
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig, description="Scheduling settings")

    @field_validator("providers", mode="before")
    @classmethod
    def inject_api_keys(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Inject API keys from environment variables."""
        env_map = {
            "claude": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "grok": "GROK_API_KEY",
            "perplexity": "PERPLEXITY_API_KEY",
        }
        for provider, env_var in env_map.items():
            if provider in v and env_var in os.environ:
                v[provider].api_key = os.environ[env_var]
        return v

    @staticmethod
    def from_yaml(path: Optional[str] = None) -> Config:
        """Load configuration from YAML file with env var overrides."""
        if path is None:
            path = os.getenv("CONFIG_PATH", str(PROJECT_ROOT / "config.yaml"))

        config_path = Path(path)
        if not config_path.exists():
            # Return defaults if no config file exists
            return Config()

        with open(config_path, "r") as f:
            data = yaml.safe_load(f) or {}

        return Config(**data)

    @staticmethod
    def from_env() -> Config:
        """Load configuration from environment variables."""
        return Config(
            general=GeneralConfig(
                question_json_path=Path(os.getenv("QUESTION_PATH", str(PROJECT_ROOT / "question.json"))),
                output_db_path=Path(os.getenv("OUTPUT_DB_PATH", str(PROJECT_ROOT / "data" / "eval_runs.db"))),
            ),
        )


# Load configuration with priority: env → yaml → defaults
try:
    if os.getenv("CONFIG_PATH"):
        config = Config.from_yaml()
    else:
        config = Config.from_yaml()
except Exception as e:
    print(f"Warning: Failed to load config: {e}. Using defaults.")
    config = Config()

# Legacy support for old env vars
QUESTION_PATH = config.general.question_json_path
OUTPUT_DB_PATH = config.general.output_db_path
