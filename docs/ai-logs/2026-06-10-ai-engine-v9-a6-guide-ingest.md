# AI Usage Log — innova-ai-engine

## Session: 2026-06-10 — Fix Pylance errors + v9 A6 `guide_ingest_worker`

**Prompt (resumen):** (1) revisar errores Pylance reportados (`reportMissingTypeStubs`
en `catalog`/`observability.logging`, `get` partially-unknown en `llm_consumer`);
(2) `/goal` continuar v7/v8/v9 del ai-engine end-to-end → elegido **v9 A6 completo
(incl. infra)**, sin commitear. Ref: `docs/PLAN_v9_ADDENDUM.md`.

### Parte 1 — errores Pylance (resueltos)

- **Causa raíz `reportMissingTypeStubs`:** el proyecto se instala **editable**
  (`_editable_impl_innova_ai_engine.pth` + `dist-info`), así que Pylance resuelve
  `src.*` como **librería instalada** y exige stubs. `pyproject.toml [tool.pyright]` ya
  pone esas reglas en `false` (pyright CLI = 0 errores), pero el Pylance **global strict**
  de Victor las reactiva. Fix: creado **`src/py.typed`** (PEP 561) → el paquete se anuncia
  tipado y el diagnóstico desaparece para todos los imports `src.`.
- **`get` partially-unknown:** los defaults literales `{}`/`[]` en `record.get(..., {})`
  infieren `dict[Unknown, Unknown]`. Reescrito `_extract_trace_id` + parseo de `Records`
  en `llm_consumer.py` con `isinstance` + `cast(dict[str, object], ...)`. Reproducido con
  un `pyrightconfig.json` temporal (strict sin overrides) y verificado limpio.
- **Bug real encontrado (no era ruido):** `client.py` tenía f-strings con saltos de línea
  dentro de `{...}` → sintaxis **solo Python 3.12+**, pero el runtime es **3.11** → habría
  dado `SyntaxError` al importar en Lambda. Corregido (líneas a una sola). `ruff check src/`
  = limpio en todo el árbol (no había más sintaxis 3.12).
- **Bug pre-existente del rename v7:** `ocr_worker.py` usaba `settings.aws_region`
  (no existe; es `app_aws_region`) → `AttributeError` en runtime + test roto. Corregido
  (mismo bug que ya había en `client.py`).

### Parte 2 — v9 A6 `guide_ingest_worker` (nuevo)

Paquete `src/guide_ingest/` con **Clean Architecture** (ports + adapters + core puro), más
el handler `src/pipeline/guide_ingest_worker.py` (trigger SQS `guide-ingest-queue`).

**Flujo (ADR v9 A6):** descarga PDF de S3 → **precheck Gemini 2.0 Flash** (kind/quality;
si `quality < umbral` → `Guide.status=EXTRACTION_FAILED` con `failure_reason` accionable y
**termina sin quemar tokens Sonnet**) → chunking ≤20 pág overlap 1 → **Sonnet 4.6** con el
PDF como **document content block** nativo, `tool_choice` forzado `extract_guide`, system
**cacheado (ephemeral)** y versionado (`# version: 9.0`) → merge de chunks (resuelve
`continues_previous` + dedup de overlap) → recorte de figuras con **pypdfium2** + render
`.tex` → S3 `guides/{id}/figures|guide.tex` → escribe `guide_questions[]` + `Guide
.status=GENERATING_SOLUTIONS` (asyncpg, una transacción) → publica `SolutionGenMessage` a
`solution-generation-queue`.

**Archivos:** `schemas.py`, `ports.py` (6 Protocols), `chunking.py`+`merge.py`+`tex.py`+
`pdf_processor.bbox_to_pixels` (core puro), `prompts.py` (system+tool), `precheck.py`
(GeminiPrecheck, `client.aio` async), `extractor.py` (SonnetExtractor, AsyncAnthropic),
`pdf_processor.py` (pypdfium2, **import lazy** para no requerir el dep en tests), `storage.py`
(S3), `publisher.py` (SQS), `repository.py` (asyncpg, tablas `guides`/`guide_questions`),
`service.py` (orquestación 100% por ports → testeable con fakes). Util nuevo
`src/shared/killswitch.py` (`PausedError`/`ensure_not_paused`).

**Contratos alineados con backend `feature/plan_V8`:** `GuideIngestMessage`
(guide_id/source_pdf_key/course_grade_level/trace_id), `SolutionGenMessage`
(guide_id/guide_question_id|null/trace_id), columnas snake_case reales del schema Prisma.

**Infra (serverless.yml):** función `guideIngest` (timeout 600, mem 2048, batchSize 1,
ReportBatchItemFailures), IAM +`s3:PutObject` +`sqs:SendMessage`, 6 env vars nuevas.
`.env.example` documentado.

**Tests:** `tests/guide_ingest/` (chunking, merge, tex, bbox, prompts, **service** con fakes
de los 6 ports: happy-path / precheck-fail / killswitch). **18 verdes.** Suite tocada:
57 passed / 1 skipped. `ruff` limpio, `pyright src/` **0 errores**, py_compile 3.11 OK.

### Decisiones / desviaciones

1. **`src/py.typed`** en vez de tocar settings del editor de Victor: arregla el
   `reportMissingTypeStubs` en la raíz (PEP 561) y es correcto (el paquete tipa estricto).
2. **Prompts en `src/guide_ingest/prompts.py`**, no en un top-level `prompts/` (el addendum
   lo dibujaba así) — respeta la regla de imports con prefijo `src.`.
3. **pypdfium2 con import lazy** dentro de los métodos → el resto del paquete y los tests
   importan sin el dep nativo instalado (Victor lo agrega).
4. **Adapters async** (`AsyncAnthropic`, `client.aio` de google-genai) por §13, en vez del
   patrón sync del `gemini_adapter` OCR existente.
5. **Killswitch compartido** (`src/shared/killswitch.py`) — `client.py` mantiene el suyo
   (refactor fuera de alcance).

**PENDIENTE VICTOR (no lo corre el agente — CLAUDE.md §0):**
```bash
cd ~/repositorios/innova/innova-ai-engine
uv add pypdfium2                 # dep nativo del recorte de figuras (A6.4)
uv run pytest tests/guide_ingest/ -q
# infra: aprovisionar guide-ingest-queue + solution-generation-queue + bucket guides
# (ya definidas en el serverless.yml del backend feature/plan_V8); exportar
# SQS_GUIDE_INGEST_ARN / SQS_SOLUTION_GEN_URL / S3_GUIDES_BUCKET antes de `serverless deploy`.
```

**Follow-up:** golden set de 10 PDFs (DoD A6: ≥90% segmentación, ≤$0.30/guía); calibrar
`bbox_to_pixels`/coordenadas contra renders reales; A7 `solution_generator` consume la cola.
