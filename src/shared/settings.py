from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    gemini_api_key: str
    database_url: str = "postgresql://localhost/innova"
    mongodb_uri: str = "mongodb://localhost/innova"
    log_level: str = "info"
    ocr_confidence_threshold: float = 0.7
    llm_batch_size: int = 20
    ssm_llm_paused_param: str = "/innova/llm/paused"
    ssm_ocr_paused_param: str = "/innova/ocr/paused"
    app_aws_region: str = "us-east-1"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
