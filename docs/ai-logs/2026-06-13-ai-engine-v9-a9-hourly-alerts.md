# AI Usage Log — innova-ai-engine

## Session: 2026-06-13 — v9 A9.2 hourly_alerts + pyright/f-string cleanup

**Prompt:** "/goal seguir trabajando en implementar v7 v8 y v9. @innova-ai-engine/docs/PLAN_v9_ADDENDUM.md" — con paste de errores de Pylance y la elección previa "A9 hourly_alerts" + criterio para `GUIDE_COMMON_ERROR` ("lo más completo posible… alineado con todos los entries en todo momento").

**Output (resumen):**

### 1. Fixes de tipado reales (reportArgumentType, CI-blocking)
El paste de Victor era mayormente ruido de Pylance editor-strict (`reportUnknown*` sobre boto3/asyncpg/pdfium — no lo aplica el `pyproject.toml`). Los errores reales:
- `guide_ingest/extractor.py` y `submission_grader/grader.py`: el `# type: ignore[arg-type]` del `messages=` quedó huérfano en su propia línea (el formatter lo movió) y no suprimía nada; inline no cabe en 88 cols → cambiado a `messages=cast(list[MessageParam], [...])` (import `from anthropic.types import MessageParam`).
- `solution_gen/repository.py`, `submission_grader/repository.py`: mismos comentarios huérfanos sobre `int(...)` multilinea → colapsados a una línea con el ignore inline.
- `solution_gen/service.py`: `set()` inferido como `set[Unknown]` → `set[str]()`.

### 2. Bug latente de runtime (f-strings multilinea PEP 701)
formatOnSave (target ≥3.12) partió f-strings en expresiones multilinea **inválidas en Python 3.11** — pyright NO las detecta. `python -m compileall src/ tests/` las cazó: `guide_ingest/tex.py` (Respuesta) y `llm_classifier/client.py` (2×). Colapsadas a una línea (<88 cols, válidas en 3.11/3.12).

### 3. A9.2 `src/alerts/` (Clean Arch, EventBridge cron horario)
- `schemas.py`: `AlertType` (AT_RISK_STUDENT, COMMON_ERROR_IN_TOPIC, STUDENT_DROP, UNIT_OFF_TRACK, GUIDE_GRADING_COMPLETE, GUIDE_COMMON_ERROR) + `MasteryRow`/`GuideProgressRow`/`GuideErrorRow`/`AlertCandidate`/`AlertRunOutcome`.
- `detectors.py` (puro): 6 detectores + helpers de severidad (LOW/MED/HIGH). `detect_guide_common_error` filtra `SPECIAL_ERROR_TYPES` leyendo la fuente única de `catalog.py` (no hardcodea codes).
- `ports.py`: `AlertRepositoryPort` (4 fetch + `insert_alert_if_absent`).
- `repository.py`: `AsyncpgAlertRepository`. Mastery scoped por lead teacher + subject. **`GUIDE_COMMON_ERROR` resuelve el errorTag en vivo**: CTE `COALESCE(override_error_tags.code, LATERAL(attempt_error_reports→error_tags via gs.attempt_id))` → siempre alineado con el catálogo a medida que crece. Insert deduped por `(teacher, alert_type, payload->>'dedup_ref', día)`.
- `service.py`: `run_hourly_alerts` orquesta 100% por el port (testeable con fake).
- `pipeline/hourly_alerts.py`: handler cron `cron(0 * * * ? *)`, sin SQS.
- `settings.py` + `serverless.yml` (`hourlyAlerts`, timeout 900/mem 1024) + `.env.example`: 7 thresholds tunables por env.
- Tests: `tests/alerts/test_detectors.py` (8) + `test_service.py` (4) = 12.

### 4. A9.4 Métricas CloudWatch (EMF)
No existía patrón `cost_usd` real en `src/` (referencia aspiracional del addendum). Elegido **EMF (Embedded Metric Format)**: se emite JSON estructurado a stdout y CloudWatch extrae las métricas — encaja con el JSONRenderer de structlog, sin `PutMetricData`/IAM/HTTP sync.
- `src/observability/metrics.py`: `build_emf` (puro, testeado) + `emit_metrics` (default dim `Stage` desde env) + constantes de nombres (7 métricas A9.4) y unidades. Namespace `Innova/Guides`.
- Wiring de las señales **ya computadas** (sin nuevo accounting): `needs_review_ratio` (solution_gen/service), `illegible_rate`/`unaligned_rate` 0/1 por submission (submission_grader/service; rate = Average en CloudWatch), `extraction_failed_count` (guide_ingest_worker, en el `except`).
- `STAGE` añadido al `provider.environment` de serverless.yml.
- Tests: `tests/observability/test_metrics.py` (3).

### 4b. A9.4 métricas de costo (token accounting plomeado por el port)
Cerradas las 3 que estaban diferidas, plomeando `response.usage` por los ports (sin acoplar el dominio al SDK):
- `src/observability/cost.py` (puro): `TokenUsage` (value object SDK-agnóstico, suma con `__add__`, props `total_input_tokens`/`cache_hit_rate`), `usage_from_response` (coalesce de los `cache_*` Opcionales de Anthropic → 0), `cost_usd(usage, model)` con tabla de precios list (`claude-sonnet-4-6`, `claude-haiku-4-5`; modelo desconocido → 0.0).
- Ports actualizados: `GuideExtractorPort.extract_chunk` y `SubmissionGraderPort.grade` ahora devuelven `tuple[Result, TokenUsage]`. Adapters (`SonnetExtractor`/`HaikuVisionGrader`) mapean `response.usage`.
- `guide_ingest/service.py`: acumula usage por chunk (`total_usage`) y emite **`ingest_cost_usd`** por guía. `submission_grader/service.py`: `_grade_with_retry` suma el usage de ambas llamadas (retry incluido) → emite **`cost_per_submission`** + **`cache_hit_rate`** en las dos ramas (illegible y graded).
- Fakes de test actualizados a la nueva firma del port (retornan `TokenUsage`). Tests: `tests/observability/test_cost.py` (7: coalesce de Opcionales, suma, cache_hit_rate, precios Haiku/Sonnet por clase de token, modelo desconocido → 0).

### 5. A9.1 `grading_eval` (scorer desacoplado + gate CLI)
El paso que genera predicciones (replay del golden set contra un `prompt_version`) es manual de Victor (§0); este módulo **sólo puntúa los registros**, así queda construible/testeable ya sin pipeline en vivo.
- `src/grading_eval/schemas.py`: `GradingEvalCase` (golden vs predicción + `cost_usd`/`latency_ms`/`illegible`/`unaligned`) y `GradingEvalReport` (accuracy, MAE, checkpoint accuracy, rates, costo, p50/p95 latencia).
- `src/grading_eval/scorer.py` (puro): `load_cases` (parse JSONL filtrando por `prompt_version`), `score_grading` (illegibles fuera de accuracy y reportados como rate; checkpoint accuracy sólo sobre casos con checkpoint golden; `unaligned_rate` sólo sobre `scored`; p50/p95 por interpolación lineal).
- `scripts/grading_eval.py`: gate CLI con `argparse` (`--input`/`--prompt-version`/`--min-accuracy` 0.85/`--max-mae` 0.15). Exit **0** pasa, **1** umbral roto, **2** sin casos. Reporte JSON a stdout (no `print()`), fallos a stderr.
- Tests: `tests/grading_eval/test_scorer.py` (8): perfect, mixed accuracy/MAE, illegible excluido, checkpoint sólo sobre golden, `unaligned_rate` sólo scored, costo/latencia (p95 interpolado 290.0), vacío todo-cero, `load_cases` parse+filtro.

### 6. Backlog v9 — Async Gemini (deuda v7)
`src/ocr/gemini_adapter.py` hacía la llamada **síncrona** `self._client.models.generate_content(...)` dentro de un port `async` (viola CLAUDE.md §13: nada de HTTP síncrono en async). Cambiado a `await self._client.aio.models.generate_content(...)`, igual que el adapter v9 `guide_ingest/precheck.py`. Test `tests/ocr/test_gemini_adapter.py` actualizado: el mock pasa de `mock_instance.models.generate_content.return_value` a `AsyncMock` sobre `mock_instance.aio.models.generate_content`. (El v9 precheck ya era async; sólo quedaba el OCR worker v7.)

**Verificación:**
- `uv run ruff check src/ tests/` → All checks passed
- `uv run pyright src/` → 0 errors, 0 warnings
- `uv run python -m compileall src/ tests/ scripts/` → sin errores de sintaxis
- `uv run pytest -q` → **149 passed, 1 skipped** (smoke) tras añadir A9.4 cost (`test_cost.py`, 7) + fix async Gemini
- Smoke CLI manual grading_eval: exit 0 (pasa), 1 (gate failed), 2 (sin casos) verificados.

**Decisión:**
- `GUIDE_COMMON_ERROR` lee el errorTag definitivo desde la fuente de verdad viva (override del profe → reporte del rule-engine/clasificador post-reprocess), filtrando sólo los sentinels `SPECIAL_ERROR_TYPES`. Cero codes hardcodeados ⇒ se mantiene alineado con los entries (304→~2540) sin tocar el detector (criterio de Victor).
- Severidad reutiliza el vocabulario `ErrorSeverity` (LOW/MED/HIGH) sobre la columna String `teacher_alerts.severity`.
- No se commitea (Victor eligió seguir sin commitear).

**Hand-off a Victor (no ejecutable por §0):** nada nuevo de infra para A9.2 (cron usa `DATABASE_URL` ya provisto). Pendiente del pipeline A6–A8: colas `solution-generation-queue`/`submission-grade-queue` + bucket de submissions + sus ARNs/URLs antes del deploy.

→ Archivo: docs/ai-logs/2026-06-13-ai-engine-v9-a9-hourly-alerts.md
