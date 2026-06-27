from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PositiveInt, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8080, alias="API_PORT")

    geo_llm_provider: Literal["mock", "openai", "chatgpt", "gemini", "ollama"] = Field(
        default="mock", alias="GEO_LLM_PROVIDER"
    )
    geo_llm_model: str = Field(default="mock-geoplanner", alias="GEO_LLM_MODEL")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    ollama_base_url: str = Field(default="http://ollama:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.1", alias="OLLAMA_MODEL")

    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_project: str = Field(default="llm-geoprocessing-prod", alias="LANGSMITH_PROJECT")

    postgis_enabled: bool = Field(default=True, alias="POSTGIS_ENABLED")
    postgis_host: str = Field(default="postgis", alias="POSTGIS_HOST")
    postgis_port: int = Field(default=5432, alias="POSTGIS_PORT")
    postgis_db: str = Field(default="geollm", alias="POSTGIS_DB")
    postgis_user: str = Field(default="geollm", alias="POSTGIS_USER")
    postgis_password: SecretStr = Field(default=SecretStr("change-me-in-prod"), alias="POSTGIS_PASSWORD")
    postgis_schema: str = Field(default="public", alias="POSTGIS_SCHEMA")

    checkpoint_backend: Literal["memory", "postgres"] = Field(default="memory", alias="CHECKPOINT_BACKEND")
    artifact_base_dir: Path = Field(default=Path("/gee_out"), alias="ARTIFACT_BASE_DIR")

    gee_plugin_url: str = Field(default="http://gee-plugin-api:8000", alias="GEE_PLUGIN_URL")
    gee_real_execution: bool = Field(default=False, alias="GEE_REAL_EXECUTION")
    gee_max_tiles_default: PositiveInt = Field(default=16, alias="GEE_MAX_TILES_DEFAULT")
    gee_max_tiles_hard_limit: PositiveInt = Field(default=128, alias="GEE_MAX_TILES_HARD_LIMIT")
    ee_private_key_path: Path = Field(default=Path("/run/secrets/gee_sa_json"), alias="EE_PRIVATE_KEY_PATH")

    request_timeout_seconds: PositiveInt = Field(default=60, alias="REQUEST_TIMEOUT_SECONDS")
    tool_timeout_seconds: PositiveInt = Field(default=600, alias="TOOL_TIMEOUT_SECONDS")
    max_bbox_area_degrees: float = Field(default=25.0, alias="MAX_BBOX_AREA_DEGREES")
    max_run_actions: PositiveInt = Field(default=8, alias="MAX_RUN_ACTIONS")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def postgres_dsn(self) -> str:
        password = self.postgis_password.get_secret_value()
        return (
            f"postgresql://{self.postgis_user}:{password}"
            f"@{self.postgis_host}:{self.postgis_port}/{self.postgis_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
