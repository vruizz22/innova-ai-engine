# AI Usage Log — innova-ai-engine

## Session: 2026-06-11 — v9 A7 `solution_generator`

**Prompt (resumen):** `/goal seguir trabajando en implementar v7 v8 y v9` tras confirmar
que Victor corrió `uv add pypdfium2` (==5.9.0) y `tests/guide_ingest/` quedó en 18 verdes
con el dep real. Lane: cerrar A6 (hecho) y avanzar al **Sprint A7** del
`docs/PLAN_v9_ADDENDUM.md`. Sin commitear.

### A7 — `solution_generator` (nuevo paquete `src/solution_gen/`)

Handler `src/pipeline/solution_generator.py` (trigger SQS `solution-generation-queue`,
batchSize 1, ReportBatchItemFailures). Consume `SolutionGenMessage` (reusado de
`src/guide_ingest/schemas.py` — single source) con `guide_question_id=None` (toda la guía)
o un id concreto (re-generación individual).

**Flujo por pregunta (ADR-118 + ADR-122):**

1. `load_guide_context` (asyncpg): join `guides → courses` + `guide_questions` con
   `COALESCE(MAX(guide_solutions.version),0)` para versionar. `subject_id`+`grade_level`
   salen del curso.
2. `fetch_topic_candidates` para el **grado del curso ±1** (`grade_window`, clamp ≥1):
   join `topics → units → curricula` filtrado por `subject_id` y rango de grado.
3. Por pregunta: `decide_mode` →
   - **VALIDATE** (`provided_solution_latex`): normaliza + `matches_provided`/`validation_notes`.
   - **DERIVE** (solo `provided_answer`): deriva y verifica que llega a la respuesta.
   - **FULL** (nada): genera desde cero (siempre `NEEDS_REVIEW`).
4. **Sonnet 4.6** (`claude-sonnet-4-6`) text-only (trabaja sobre `statement_latex`, no el
   PDF → mucho más barato que A6), tool forzado `generate_solution`, system cacheado
   ephemeral `# version: 9.0`. Output: `topic_code`+`topic_confidence`, `final_answer`,
   `steps[]` (latex/explanation_es/checkpoint/expected_error_tags), `alt_paths[]`,
   `validation_notes`, `matches_provided`.
5. Resuelve `topic_code` → `topic_id`/`domain_id`/`subdomain_id` (mapa de candidatos).
   `fetch_active_error_codes(domain_id)` + `sanitize_solution` → **filtra los
   `expected_error_tags` al catálogo ACTIVE del dominio** (ADR A7.2; dominio no resuelto ⇒
   tags vacíos).
6. `resolve_status`: `NEEDS_REVIEW` si topic no resuelto / confianza < 0.85 / FULL /
   `matches_provided=false` / hay `validation_notes`; si no, `EXTRACTED`. `source` =
   `PDF_PROVIDED` (VALIDATE) | `LLM_GENERATED` (DERIVE/FULL).
7. `save_solution` (1 txn): baja `is_current` previo, inserta `guide_solutions`
   (`steps_json` jsonb canónico, `expected_error_tags` text[]), actualiza
   `guide_questions` (status/topic/confidence, `topic_source='LLM'`).
8. Cierre: si `count_unsolved(guide)==0` → `mark_guide_review_and_alert`: `Guide.status=REVIEW`
   + `TeacherAlert(GUIDE_READY_FOR_REVIEW)` **deduped** por `payload->>'guide_id'` con
   `resolved_at IS NULL`.

**Clean Architecture:** `schemas.py` (Pydantic strict), `ports.py` (2 Protocols:
generator + repo), `domain.py` (núcleo puro: `decide_mode`, `grade_window`,
`solution_source`, `index_candidates`, `sanitize_solution`, `collect_error_tags`,
`resolve_status`), `prompts.py` (system+tool versionado), `generator.py`
(`SonnetSolutionGenerator`, `AsyncAnthropic`, killswitch), `repository.py`
(`AsyncpgSolutionRepository`), `service.py` (orquesta 100% por ports).

**Settings nuevos** (`src/shared/settings.py`): `ssm_guides_solution_paused_param`
(`/innova/guides/solution_paused`), `solution_gen_use_batches=True`,
`solution_topic_min_confidence=0.85`. **Infra:** `serverless.yml` función
`solutionGenerator` (timeout 600, mem 1024) + 3 env vars; `.env.example` con
`SQS_SOLUTION_GEN_ARN` (trigger; A6 publica al mismo queue vía `SQS_SOLUTION_GEN_URL`).

### Bug latente de A6 corregido (mismo sprint)

`guide_ingest/repository._INSERT_QUESTION` omitía `id` y `updated_at` — ambos
`TEXT/TIMESTAMP NOT NULL` **sin default en DB** (Prisma genera el uuid client-side, no
crea default Postgres). Habría fallado en runtime contra la DB real (los tests A6 usan
fake repo, por eso no se vio). Fix: `id = gen_random_uuid()`, `updated_at = NOW()`. El
mismo patrón se aplicó a los INSERT de A7 (`guide_solutions`, `teacher_alerts`).

### Detalles técnicos verificados contra la migración real

- Enums nativos Postgres `"GuideQuestionStatus"`/`"SolutionSource"` (migración
  `20260611223114_v9_guides_pipeline`) → los params enum se castean explícitamente
  (`$n::"GuideQuestionStatus"`) porque asyncpg envía texto tipado, no literal unknown.
- `guide_solutions.steps_json` JSONB → se pasa string + `$5::jsonb`.
  `expected_error_tags` TEXT[] → lista Python directa.
- `pdf_processor._RENDER_SCALE` 2.0 → 2: con pypdfium2 ya instalado, pyright resuelve el
  stub real y `render(scale: int)` rechazaba el float; 2 y 2.0 renderizan idéntico.

### Verificación

`ruff src/ tests/` limpio · `pyright src/` **0 errores** · **A7: 25 tests** (domain 13,
prompts 4, service 8 con fakes de los 2 ports: FULL→NEEDS_REVIEW, VALIDATE-match→EXTRACTED,
DERIVE-mismatch→REVIEW, tags filtrados al catálogo, topic no resuelto, steps_json canónico,
killswitch, guía inexistente). Suite completa **102 passed / 1 skipped** (sin `--cov`,
§0). py_compile 3.11 OK. `serverless.yml` válido (`solutionGenerator` presente).

### Decisiones / desviaciones

1. **1 llamada Sonnet por pregunta** (no batches de 1-5). Más simple/testeable; el flag
   `SOLUTION_GEN_USE_BATCHES` queda en settings para cablear la Batches API (-50%) como
   follow-up. La clasificación de topic va **en el mismo tool** (`generate_solution`
   devuelve `topic_code`+`topic_confidence`), evitando una segunda llamada.
2. **expected_error_tags filtrados post-hoc** al catálogo ACTIVE del dominio (en vez de
   inyectar todos los catálogos de grado ±1 en el prompt). Garantiza códigos reales sin
   inflar el prompt; los tags se refinan luego en A8/classifier.
3. **`solution_latex` = NULL** al persistir (render derivado del wizard, no fuente de
   verdad — coincide con el comentario del schema).
4. **Sin SQS de salida en A7** (sprint terminal hasta revisión del profe); solo escribe
   `guide_solutions` + flip a REVIEW + alerta.

**PENDIENTE VICTOR (no lo corre el agente — CLAUDE.md §0):**
```bash
cd ~/repositorios/innova/innova-ai-engine
# A7 no agrega deps. Solo infra:
# aprovisionar/confirmar solution-generation-queue y exportar su ARN como
# SQS_SOLUTION_GEN_ARN (= mismo queue al que A6 publica vía SQS_SOLUTION_GEN_URL)
# antes de `serverless deploy`.
```

**Follow-up:** A8 `submission_grader` (Haiku vision, cola `submission-grade-queue`);
golden set de pautas (DoD A7: ≥90% correctas, topic accuracy ≥85%); cablear Batches API.
