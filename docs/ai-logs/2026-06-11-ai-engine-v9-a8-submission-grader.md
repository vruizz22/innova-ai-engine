# AI Usage Log — innova-ai-engine

## Session: 2026-06-11 — v9 A8 `submission_grader`

**Prompt (resumen):** `/goal seguir trabajando en implementar v7 v8 y v9`. Tras cerrar A6
(dep instalado) y A7 (construido+verificado), continúo al **Sprint A8** del
`docs/PLAN_v9_ADDENDUM.md`. Sin commitear.

### A8 — `submission_grader` (nuevo paquete `src/submission_grader/`)

Handler `src/pipeline/submission_grader.py` (trigger SQS `submission-grade-queue`,
batchSize 5, ReportBatchItemFailures). Consume `GradeSubmissionMessage`
(`guide_submission_id`+`trace_id`, mínimo; el worker carga fotos+pauta de la DB).

**Flujo (ADR v9 A8.1, ADR-121):**

1. `load_submission_context` (asyncpg): join `guide_submissions → guide_questions →
   guides → courses` + `guide_solutions` (current) + extracto del catálogo del dominio
   (reusa `get_domain_catalog` del classifier v8). Sin pauta vigente ⇒ None (espera a A7).
2. Descarga 1-3 fotos de S3 (`photo_keys`, bucket `s3_submissions_bucket`).
3. **Haiku 4.5 vision** (`claude-haiku-4-5`), **una llamada por submission**, tool forzado
   `transcribe_and_align`. **Dos bloques `system` cacheados (ephemeral):** (a) grading
   prompt estático, (b) bloque por-pregunta `<official_solution>`+`<error_catalog>` que
   comparten las ~35 entregas de esa pregunta (clave lógica guía/pregunta/solutionVersion;
   el catálogo ancla el mínimo cacheable de Haiku).
4. Output canónico: `transcription{steps[idx/latex/legible], final_answer, confidence}` +
   `alignment{matches[verdict OK|ERROR|SKIPPED], path MAIN|ALT_<n>|UNALIGNED}` +
   `provisional{is_correct, score_0_1, first_error_step_idx}`. **El grader NO asigna error
   tags** (ADR-121) — el tag definitivo sale del rule engine/classifier del backend.
5. **Confianza < umbral ⇒ 1 reintento**; si sigue baja ⇒ cierra `GRADED` con
   `failure_reason=ILLEGIBLE` (profe ve foto + transcripción parcial), **sin reprocess**.
6. Legible ⇒ escribe `GuideSubmission(status=GRADING, transcription*/alignment_json/score/
   is_correct/solution_version)` y publica `ReprocessMessage` (`attempt_id=null`,
   `guide_submission_id`, `guide_question_id`, `latex_steps[]`, `provider="claude-haiku"`,
   `confidence`, `alignment_summary{path, first_error_checkpoint, score_0_1}`) a la cola
   **existente `attempt-reprocess-queue`** (`sqs_attempt_reprocess_url`).

**Clean Architecture:** `schemas.py` (Pydantic strict), `ports.py` (2 Protocols:
grader + repo; **reusa `ObjectStorePort`/`MessagePublisherPort` de A6**), `domain.py`
(núcleo puro: `cache_key`, `is_legible`, `transcription_latex`, `latex_steps`,
`summarize_alignment`), `prompts.py` (system+pauta-block+tool versionado), `grader.py`
(`HaikuVisionGrader`, `AsyncAnthropic`, killswitch `grading_paused`), `repository.py`
(`AsyncpgSubmissionRepository`), `service.py` (orquesta 100% por ports). El handler reusa
`S3ObjectStore(bucket=s3_submissions_bucket)` y `SqsPublisher` de A6.

**Settings nuevos** (`src/shared/settings.py`): `sqs_attempt_reprocess_url`,
`s3_submissions_bucket`, `ssm_guides_grading_paused_param`, `ssm_guides_cheap_mode_param`,
`grading_min_transcription_confidence=0.5`. **Infra:** `serverless.yml` función
`submissionGrader` (timeout 120, mem 512, batchSize 5) + 5 env vars; `.env.example` con
`SQS_SUBMISSION_GRADE_ARN`/`SQS_ATTEMPT_REPROCESS_URL`/`S3_SUBMISSIONS_BUCKET`.

### Detalles técnicos

- Enum `"SubmissionStatus"` casteado en el UPDATE (`$2::"SubmissionStatus"`);
  `transcription_json`/`alignment_json` JSONB (`$n::jsonb`); `graded_at=NOW()` solo en la
  rama `GRADED`.
- Bloque de imagen vision reutiliza el formato ya probado del repo
  (`{type:image, source:{base64, image/jpeg}}` del `ocr/claude_adapter.py`).
- Cheap mode (`grading_cheap_mode`: Gemini transcribe + Haiku texto) queda **como
  follow-up** (settings + SSM param cableados); A8 implementa la ruta vision del DoD.

### Verificación

`ruff src/ tests/` limpio · `pyright src/` **0 errores** · **A8: 17 tests** (domain 6,
prompts 5, service 6 con fakes grader/store/publisher/repo: legible→GRADING+reprocess,
retry-then-success, illegible→GRADED-sin-reprocess, sin-fotos→FAILED, sin-contexto→FAILED,
killswitch). **Suite completa 119 passed / 1 skipped** (sin `--cov`, §0). py_compile 3.11
OK. `serverless.yml` válido — 8 funciones (`health, llmClassifier, nightlyBkt, nightlyIrt,
ocrWorker, guideIngest, solutionGenerator, submissionGrader`).

### Estado del pipeline v9 (este repo)

**A6 → A7 → A8 completos y verificados** end-to-end (Clean Arch, ports+adapters, 60 tests
nuevos entre los tres). Falta **A9** (eval scripts `grading_eval.py`, `hourly_alerts.py`
deuda v7 + tipos v9, load test, métricas CloudWatch) + track paralelo v8 (catálogo →2540,
prompts by_domain).

**PENDIENTE VICTOR (no lo corre el agente — CLAUDE.md §0):**
```bash
cd ~/repositorios/innova/innova-ai-engine
# A8 no agrega deps. Solo infra:
# aprovisionar submission-grade-queue + bucket de submissions; confirmar
# attempt-reprocess-queue (ya existe del loop OCR v7). Exportar
# SQS_SUBMISSION_GRADE_ARN / SQS_ATTEMPT_REPROCESS_URL / S3_SUBMISSIONS_BUCKET antes del deploy.
```

**Follow-up:** A9 (`hourly_alerts` es prerequisito del piloto), golden set de 100 entregas
manuscritas (DoD A8: transcripción ≥90%, alineación ≥80%, ≤$0.006/pregunta, cache >70%),
cheap mode.
