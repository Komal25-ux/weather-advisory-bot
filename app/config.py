from typing import Literal, List
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env file."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server settings
    HOST: str = Field(default="0.0.0.0", description="FastAPI bind host")
    PORT: int = Field(default=8000, description="FastAPI bind port")
    ENVIRONMENT: Literal["development", "production", "test"] = Field(
        default="development",
        description="Deployment environment"
    )
    LOG_LEVEL: str = Field(default="INFO", description="Application logging level")

    # LLM Settings (Defaults to Google Gemini OpenAI-compatible endpoint)
    LLM_PROVIDER: str = Field(default="gemini", description="Configurable LLM provider: gemini, openai")
    LLM_API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"),
        description="API key for LLM provider"
    )
    LLM_MODEL: str = Field(default="gemini-3.6-flash", description="Primary LLM model identifier")
    LLM_FALLBACK_MODELS: str = Field(
        default="gemini-3.5-flash,gemini-3.5-flash-lite",
        description="Comma-separated fallback models for provider resilience"
    )
    LLM_BASE_URL: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        description="LLM API base URL"
    )
    LLM_TIMEOUT_SECONDS: float = Field(default=15.0, description="LLM request timeout in seconds")

    @property
    def effective_llm_models(self) -> List[str]:
        """Constructs effective ordered list of models without duplicates."""
        primary = self.LLM_MODEL.strip() if self.LLM_MODEL else ""
        fallbacks = [m.strip() for m in self.LLM_FALLBACK_MODELS.split(",") if m.strip()]
        models = [primary] if primary else []
        for m in fallbacks:
            if m not in models:
                models.append(m)
        return models

    # Open-Meteo Settings (No API key needed)
    GEOCODING_BASE_URL: str = Field(
        default="https://geocoding-api.open-meteo.com/v1/search",
        description="Open-Meteo Geocoding API endpoint"
    )
    FORECAST_BASE_URL: str = Field(
        default="https://api.open-meteo.com/v1/forecast",
        description="Open-Meteo Forecast API endpoint"
    )
    OPEN_METEO_TIMEOUT_SECONDS: float = Field(
        default=8.0,
        description="Open-Meteo HTTP request timeout"
    )

    # Policies directory path
    SOPS_DIR: str = Field(default="sops", description="Path to externalized YAML SOP definitions")


settings = Settings()
