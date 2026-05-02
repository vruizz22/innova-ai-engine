# CLAUDE.md — innova-ai-engine

> Repo-specific instructions for Claude Code. Inherits all rules from `~/.claude/CLAUDE.md`.
> Stack: Python 3.11 + uv + Pydantic v2 + Anthropic SDK + Google Generative AI + scipy + numpy + AWS Lambda.

---

## [1] Domain context

This repo houses all **ML/AI compute workers** for Innova EdTech:

1. **BKT Calibrator** (`src/bkt/`) — nightly brute-force grid search over `(p_L0, p_T, p_S, p_G)` per skill.
2. **IRT Calibrator** (`src/irt/`) — nightly `scipy` 2PL maximum-likelihood fit of `(a, b)` per item.
3. **LLM Error Classifier** (`src/llm_classifier/`) — Anthropic Claude Haiku 4.5, batch 20 attempts, prompt caching, tool_use forced.
4. **OCR Vision Worker** (`src/ocr/`) — Gemini 2.0 Flash Vision (primary) + Claude Vision fallback via `MathOCRPort`.
5. **Lambda handlers** (`src/pipeline/`) — independently deployable, SQS/S3/EventBridge triggers.

---

## [2] Package manager and tooling

- **Package manager: `uv` ONLY**. Never `pip install` directly. Use `uv add <pkg>` and `uv run <cmd>`.
- **Type checking: `pyright` strict** — zero warnings. CI blocks on any pyright error.
- **Lint/format: `ruff` + `ruff format`** — run `uv run ruff check src/ tests/` before committing.
- Python version: `3.11` (specified in `.python-version`).
- Virtual environment: managed by `uv` at `.venv/`.

---

## [3] Strict Python rules

- `from __future__ import annotations` at top of every module.
- **NEVER `dict[str, Any]`** without explicit justification in a comment.
- **NEVER `print()`** — only `structlog` JSON logging.
- Type hints mandatory on all functions, including private helpers.
- Pydantic v2 for ALL schemas (request/response/config). No plain dataclasses for domain schemas.
- `pyright` configured in `pyproject.toml` with `pythonVersion = "3.11"`, `strict = true`.
- `ruff` rules: `E, F, I, N, UP, B, RUF` enabled.
- always use import aliases for internal imports — e.g. `from src.shared import postgres` — never relative imports or absolute imports without `src.` prefix.

---

## [4] BKT calibration conventions

Path: `src/bkt/`

- `update.py`: closed-form online update (reference implementation; production uses TS port in backend).
- `calibrate.py`: brute-force grid search. Grid: `p_L0 ∈ [0.05, 0.95]` step 0.05, same for `p_T, p_S, p_G`. Minimize negative log-likelihood over attempt history per skill. Writes results back to Postgres.
- `schemas.py`: `BktParams(BaseModel)` with fields `p_l0, p_transit, p_slip, p_guess` (all `float`, range `[0,1]`).
- Algorithm reference: Corbett & Anderson (1995). See `docs/.github/instructions/04-modelo-cognitivo.md` §4.1.
- Key constraint: `p_slip + p_guess < 1.0` must be enforced as a validation constraint.

---

## [5] IRT calibration conventions

Path: `src/irt/`

- `two_pl.py`: fits 2PL model using `scipy.optimize.minimize` with `method='L-BFGS-B'`. Minimize negative log-likelihood. Per-item fit: `(a ∈ [0.5, 3.0], b ∈ [-3, 3])`.
- `fisher.py`: computes Fisher information `I(θ) = a² * P(θ) * (1-P(θ))` for item selection.
- `schemas.py`: `IrtItemParams(BaseModel)` with `item_id: str`, `a: float`, `b: float`.
- Algorithm reference: Lord (1980). See `docs/.github/instructions/04-modelo-cognitivo.md` §4.2.
- Minimum attempts per item before calibrating: **50**. Below that, keep defaults `a=1.0, b=0.0`.

---

## [6] LLM classifier conventions

Path: `src/llm_classifier/`

- `client.py`: Anthropic SDK wrapper. **`cache_control: {"type": "ephemeral"}` MUST be set on system prompt block**. Fails CI if missing.
- `tools.py`: `tool_use` schema with `name="classify_errors"`, input schema with `attempts: list[AttemptClassification]`. Tool choice: `{"type": "tool", "name": "classify_errors"}` — forced, never "auto".
- `prompts.py`: versioned system prompt with `# version: X.Y` comment. Few-shot examples live in the system prompt (cached). User prompt contains only the batch of 20 attempts JSON.
- `batch.py`: assembles batches of 20 from SQS messages, calls `client.py`, parses tool_use response, writes results to Postgres via asyncpg.
- **Cost killswitch**: check SSM Parameter `/innova/llm/paused` before every API call. If `true`, drop to DLQ with `paused_due_to_cost` metadata.
- Model: `claude-haiku-4-5` (never sonnet/opus in prod — cost constraint).
- No PII in prompts: only `attempt_id` (UUID), `rawSteps`, `topic`. Never student name/email.

---

## [7] OCR vision worker conventions

Path: `src/ocr/`

- `ports.py`: defines `MathOCRPort` — a `Protocol` class with `async def extract(image_bytes: bytes, trace_id: str) -> OcrResult`.
- `gemini_adapter.py`: implements `MathOCRPort` using `google-generativeai`. Model: `gemini-2.0-flash`. Prompt instructs extraction of math steps as structured JSON.
- `claude_adapter.py`: implements `MathOCRPort` using Anthropic Vision. Fallback only.
- `orchestrator.py`: calls Gemini → if `overall_confidence < 0.7`, escalate to Claude fallback. Returns `OcrResult` with `latex_steps: list[str]`, `overall_confidence: float`, `provider: str`.
- **Cost killswitch**: check SSM Parameter `/innova/ocr/paused` before every API call.
- Image filenames from S3: always `{uuid}.jpg` — EXIF-stripped, no PII in filename.
- `schemas.py`: `OcrResult(BaseModel)`, `OcrProvider(str, Enum)` with values `GEMINI | CLAUDE`.

---

## [8] Lambda handler conventions

Path: `src/pipeline/`

- `nightly_bkt.py`: EventBridge cron trigger `cron(0 7 * * ? *)`. Loads all skills, loads attempt history from Postgres, runs BKT grid search per skill, writes params back.
- `nightly_irt.py`: EventBridge cron `cron(15 7 * * ? *)`. Loads items with ≥50 attempts, runs IRT fit per item, writes `(a, b)` back.
- `llm_consumer.py`: SQS Standard trigger, `BatchSize=20, MaximumBatchingWindowInSeconds=60`. Deserializes messages, calls `batch.py`, handles partial batch failures.
- `ocr_worker.py`: S3 event trigger on `uploads/` prefix. Downloads image, calls `orchestrator.py`, posts structured result to `innova-backend-serverless` via API or directly to Postgres.
- All handlers: extract `trace_id` from SQS `MessageAttributes` or generate new UUID. Propagate to all child calls via `structlog.contextvars.bind_contextvars(trace_id=...)`.
- Handler signature: `def handler(event: dict[str, object], context: object) -> dict[str, object]`.

---

## [9] Observability

Path: `src/observability/`

- `logging.py`: configure `structlog` with JSON renderer, `trace_id` bound at Lambda entry.
- `tracing.py`: `bind_trace_id(trace_id: str)` helper that calls `structlog.contextvars.bind_contextvars`.
- Every log call: `logger.info("event_name", attempt_id=..., skill=..., duration_ms=...)`.
- **No `print()` anywhere** — ruff rule `T201` will catch it.

---

## [10] Database access

Path: `src/shared/postgres.py`

- `asyncpg` connection pool. Pool initialized once per Lambda cold start via `asynccontextmanager`.
- **No synchronous DB calls** — all `await conn.*`.
- `DATABASE_URL` from environment (validated at boot via `pydantic.BaseSettings`).
- Queries typed with `asyncpg`'s return types — wrap in typed helper functions, no raw result tuples exposed.

---

## [11] Settings validation

Path: `src/shared/settings.py`

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    anthropic_api_key: str
    gemini_api_key: str
    database_url: str
    mongodb_uri: str
    log_level: str = "info"
    ocr_confidence_threshold: float = 0.7
    llm_batch_size: int = 20
    ssm_llm_paused_param: str = "/innova/llm/paused"
    ssm_ocr_paused_param: str = "/innova/ocr/paused"

    model_config = SettingsConfigDict(env_file=".env")
```

Call `Settings()` once at module level — do not pass as function args through every layer.

---

## [12] Testing requirements

- `pytest` ≥7 + `hypothesis` ≥6 + `pytest-asyncio` + `pytest-cov`.
- Coverage gate: **≥75%** (`pytest --cov-fail-under=75`).
- BKT: property-based tests (`hypothesis`) for bounds `[0,1]`, monotonicity, idempotency. Recovery test with 1000 synthetic attempts.
- IRT: recovery test — synthetic 2PL data, verify `|a_recovered - a_true| < 0.2` for 90th percentile.
- LLM classifier: mock `anthropic.Anthropic` client. Assert `cache_control` block present. Assert `tool_choice` forced. Assert response parsing handles `tool_use` block.
- OCR: mock Gemini + Claude responses, assert `OcrResult` schema conformance. Smoke test (1 real image) runs once in CI with `@pytest.mark.smoke`.
- Lambda handlers: `moto` for SQS/S3 mocks.

See `docs/prompt/02-innova-ai-engine-testing.md` for full test spec.

---

## [13] What NOT to do

- No `scikit-learn`, no `torch`, no `tensorflow` in production runtime.
- No Modal.com in MVP (ADR-002 in `docs/architecture.md`).
- No `Any` in type hints without `# type: ignore[assignment]` + justification comment.
- No synchronous HTTP calls — use `httpx.AsyncClient` or SDK async methods.
- No image processing locally — always delegate to Vision API.
- No LLM call without `cache_control` on system prompt block.
