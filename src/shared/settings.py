from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    gemini_api_key: str
    database_url: str = "postgresql://localhost/innova"
    mongodb_uri: str = "mongodb://localhost/innova"
    log_level: str = "info"
    # Gemini model for OCR (src/ocr) + PDF precheck (A6). Env-overridable so a project
    # whose free tier returns limit:0 for one model can switch without code changes.
    # NOTE: gemini-2.0-flash was shut down 2026-06-01 — default is now 2.5-flash.
    gemini_model: str = "gemini-2.5-flash"
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

    # v9 guides pipeline — A10 adhoc_solver (scan without guide context)
    sqs_adhoc_solve_url: str = ""

    # B1/B2 exercise_generator (teacher-triggered AI generation)
    sqs_exercise_generate_url: str = ""

    # M11 / A9.2 hourly_alerts (EventBridge cron) — detector thresholds
    alert_at_risk_pknown_floor: float = 0.4
    alert_at_risk_min_topics: int = 3
    alert_topic_struggle_ratio: float = 0.5
    alert_student_drop_trend: float = -0.15
    alert_unit_off_track_floor: float = 0.4
    alert_guide_complete_ratio: float = 0.9
    alert_guide_common_error_ratio: float = 0.3


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
