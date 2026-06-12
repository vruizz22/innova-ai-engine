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

    # v9 guides pipeline — A6 guide_ingest_worker
    sqs_solution_gen_url: str = ""
    s3_guides_bucket: str = ""
    ssm_guides_ingest_paused_param: str = "/innova/guides/ingest_paused"
    guide_ingest_chunk_pages: int = 20
    guide_ingest_chunk_overlap: int = 1
    guide_min_extraction_quality: float = 0.5

    # v9 guides pipeline — A7 solution_generator
    ssm_guides_solution_paused_param: str = "/innova/guides/solution_paused"
    solution_gen_use_batches: bool = True
    solution_topic_min_confidence: float = 0.85

    # v9 guides pipeline — A8 submission_grader
    sqs_attempt_reprocess_url: str = ""
    s3_submissions_bucket: str = ""
    ssm_guides_grading_paused_param: str = "/innova/guides/grading_paused"
    ssm_guides_cheap_mode_param: str = "/innova/guides/grading_cheap_mode"
    grading_min_transcription_confidence: float = 0.5


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
