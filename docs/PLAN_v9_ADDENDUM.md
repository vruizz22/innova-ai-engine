# PLAN v9 — Addendum innova-ai-engine

> v9 · 2026-06-10 · Supersede `PLAN_v8_ADDENDUM.md` (los pendientes v8 quedan embebidos como **track paralelo**).
> Master plan: `../../docs/MASTER_PLAN_v9.md`. ADRs: 116-125 (y 101-115 vigentes).
> **Regla #0:** ver `CLAUDE.md §0` — el agente NO ejecuta `uv sync/add`, `serverless deploy`, suites pytest largas.

---

## Contexto: dónde estamos

✅ **Hecho (v7/v8):**

- OCR (Gemini 2.0 Flash → Claude fallback) vía `MathOCRPort` + `orchestrator.py`.
- LLM classifier con routing por dominio (`classify_batch_for_domain`, `DomainCatalog`, grouper en `llm_consumer.py`) — rama `feature/assignment`, **parcialmente sin commitear** (⚠️ commitear antes de iniciar A6).
- BKT/IRT calibradores nightly.
- Catálogo: 341 entries generadas/importadas (batch scripts en `scripts/`).

🔴 **Deuda v7/v8 que se absorbe en v9:**

- `src/pipeline/hourly_alerts.py` no existe → entra en **A9**.
- Prompts `prompts/by_domain/*.py` (19 dominios) parcialmente materializados → **track paralelo** (requisito para clasificar entregas de guías de cualquier dominio).
- `error_catalog_generator.py` formal (los batch scripts actuales son ad-hoc) → **track paralelo**.

🟡 **v9 nuevo:** 3 workers del pipeline de guías: `guide_ingest_worker`, `solution_generator`, `submission_grader`.

---

## Sprint A6 (M23 — `guide_ingest_worker`)

Nuevo paquete `src/guide_ingest/` + handler `src/pipeline/guide_ingest_worker.py` (SQS trigger `guide-ingest-queue`).

### A6.1 Flujo

1. Descarga PDF de S3 (`Guide.sourcePdfKey`).
2. **Precheck Gemini 2.0 Flash** (reusa adapter pattern existente): `{kind: SCANNED|DIGITAL|MIXED, content_pages: list[int], quality: float}`. Si `quality < umbral` → `Guide.status=EXTRACTION_FAILED` con `failure_reason` accionable ("re-escanea a 300dpi, páginas 3-5 ilegibles") y **termina** (no quema tokens Sonnet).
3. **Sonnet 4.6** (`claude-sonnet-4-6`): PDF como **document content block nativo** (chunks de ≤20 páginas, overlap de 1 página para preguntas cortadas). `tool_choice` forzado a `extract_guide`. System prompt cacheado (`cache_control: ephemeral`) y versionado (`# version: 9.x`).
4. Merge de chunks (resolver `continues_previous`), recorte de figuras con `pypdfium2` server-side (sin Vision, usa `figure_bboxes`) → S3 `guides/{id}/figures/`, render del `.tex` completo → S3 `guides/{id}/guide.tex` (ADR-117).
5. Escribe `GuideQuestion[]` vía asyncpg (patrón `src/shared/postgres.py`), `Guide.status=GENERATING_SOLUTIONS`, publica a `solution-generation-queue`.

### A6.2 Tool schema `extract_guide`

```python
class ExtractedQuestion(BaseModel):
    label: str | None            # "1.a", "3", "II.2"
    statement_latex: str
    statement_text: str
    provided_answer: str | None
    provided_solution_latex: str | None
    figure_bboxes: list[FigureBBox]   # page, x0, y0, x1, y1
    continues_previous: bool          # pregunta cortada entre chunks
```

### A6.3 Guardrails

- Killswitch SSM `/innova/guides/ingest_paused` antes de cada llamada (patrón existente).
- structlog con `trace_id` propagado desde el mensaje SQS.
- Pydantic strict en todos los schemas; pyright strict.

**DoD A6:** golden set de 10 PDFs (5 digitales + 5 escaneados) → ≥90% de preguntas correctamente segmentadas; costo medido ≤$0.30/guía; `EXTRACTION_FAILED` con mensajes accionables en los casos malos.

---

## Sprint A7 (M23 — `solution_generator`)

Nuevo paquete `src/solution_gen/` + handler `src/pipeline/solution_generator.py` (SQS trigger `solution-generation-queue`).

### A7.1 Flujo por pregunta (batch por guía, llamadas de a 1-5 preguntas)

Sonnet 4.6 con tool forzado `generate_solution` → **formato canónico ADR-118** (`steps[]` con latex/explanation_es/checkpoint/expected_error_tags, `alt_paths[]`, `final_answer`, `points`).

Tres modos según lo que trajo el PDF:

| Modo | Condición | Comportamiento |
|---|---|---|
| **VALIDATE** | `provided_solution_latex` existe | Normaliza al formato canónico; si discrepa del solucionario del PDF → `validation_notes` + `GuideQuestion.status=NEEDS_REVIEW` |
| **DERIVE** | solo `provided_answer` | Genera el desarrollo y **verifica que llegue a esa respuesta**; si no llega → `NEEDS_REVIEW` (probable error en el PDF o en la extracción) |
| **FULL** | nada | Genera desarrollo + respuesta desde cero → siempre revisable en wizard |

### A7.2 Clasificación de topic (ADR-122)

El prompt incluye la lista compacta `Unit/Topic` del grado del curso ±1 (query Postgres, cacheada por grado en memoria del Lambda). Output: `{topic_code, confidence}` por pregunta. `confidence < 0.85` → `NEEDS_REVIEW`.

Además: `expected_error_tags` se eligen del catálogo ACTIVE del dominio clasificado (query vía `DomainCatalog` existente).

### A7.3 Cierre

- Cuando todas las preguntas tienen pauta: `Guide.status=REVIEW` + insert `TeacherAlert(GUIDE_READY_FOR_REVIEW)` vía asyncpg.
- Soporta re-generación individual (mensaje con `guide_question_id`).
- Flag `SOLUTION_GEN_USE_BATCHES=true` → usa **Batches API** (-50%) cuando SLA <1h es aceptable (colegios suben guías con días de anticipación; default ON, OFF para demo/dev).

**DoD A7:** pautas del golden set ≥90% correctas tras revisión humana; topic accuracy ≥85% vs etiquetado manual; `validation_notes` detecta las discrepancias plantadas en el golden set.

---

## Sprint A8 (M25 — `submission_grader`)

Nuevo paquete `src/submission_grader/` + handler `src/pipeline/submission_grader.py` (SQS trigger `submission-grade-queue`, BatchSize=5).

### A8.1 Flujo

1. Descarga 1-3 fotos de S3 (`photoKeys`).
2. **Haiku 4.5 vision** (`claude-haiku-4-5`), **una llamada por submission**:
   - Bloque cacheado (`cache_control: ephemeral`, TTL 1h): system grading prompt + pauta canónica de la pregunta (current version) + extracto del catálogo de errores del dominio. El bloque debe superar el **mínimo cacheable de 4096 tokens** de Haiku — se ancla con el extracto del catálogo. Cache key efectiva: (guía, pregunta, solutionVersion). Las ~35 entregas del curso comparten el bloque.
   - User: imágenes + metadatos (grado, label de la pregunta).
   - Tool forzado `transcribe_and_align`:

```python
class TranscribeAndAlign(BaseModel):
    transcription: Transcription      # steps[{idx, latex, legible}], final_answer, confidence
    alignment: Alignment              # matches[{student_step_idx, solution_checkpoint_idx, verdict: OK|ERROR|SKIPPED}]
                                      # path: MAIN | ALT_<n> | UNALIGNED
    provisional: Provisional          # is_correct, score_0_1, first_error_step_idx | None
```

3. **El grader NO asigna error tags** (ADR-121) — entrega transcripción + alineación + veredicto por paso; el tag definitivo sale del rule engine o del LLM classifier by_domain del backend.
4. Escribe `transcription*/alignment_json/score provisional` en `GuideSubmission(status=GRADING)` y publica a **`attempt-reprocess-queue` existente**:

```json
{
  "attempt_id": null,
  "guide_submission_id": "uuid",
  "guide_question_id": "uuid",
  "latex_steps": ["..."],
  "provider": "claude-haiku",
  "confidence": 0.91,
  "alignment_summary": { "path": "MAIN", "first_error_checkpoint": 2, "score_0_1": 0.5 },
  "trace_id": "uuid"
}
```

### A8.2 Fallbacks y guardrails

- `transcription.confidence < 0.5` → 1 reintento; si sigue bajo → cierra `GRADED` con veredicto `ILLEGIBLE` (el profe ve foto + transcripción parcial y puede corregir a mano).
- Killswitch `/innova/guides/grading_paused`.
- `/innova/guides/grading_cheap_mode=true` → Gemini transcribe (adapter existente) + Haiku **texto-only** alinea (baja costo ~45%, baja precisión — solo bajo presión de presupuesto).
- Métrica de costo por llamada acumulada en CloudWatch (patrón `cost_usd` del OCR existente).

**DoD A8:** golden set de 100 entregas manuscritas reales → transcripción útil ≥90%, alineación correcta ≥80%, costo ≤$0.006/pregunta, cache hit rate >70%, p95 foto→publicación a reprocess <60s (el cierre total <90s lo mide backend).

---

## Sprint A9 (M27 — Evaluación, alertas, load test)

### A9.1 `scripts/grading_eval.py` (NUEVO)

Corre los golden sets (extracción, pauta, grading) contra una versión de prompts y reporta accuracy/costo/latencia. **Gate manual** antes de cada release de prompt (`prompt_version` en DB permite comparar).

### A9.2 `src/pipeline/hourly_alerts.py` — se salda la deuda v7

- Tipos v7: `AT_RISK_STUDENT | COMMON_ERROR_IN_TOPIC | STUDENT_DROP | UNIT_OFF_TRACK` (+ `domain_id`/`subdomain_code` en payload).
- Tipos v9 nuevos: `GUIDE_GRADING_COMPLETE` (>90% del curso GRADED en una guía) y `GUIDE_COMMON_ERROR` (mismo errorTag en >30% del curso en una misma pregunta).
- Dedup `(teacher_id, alert_type, guide_id|topic_id, day)`.

### A9.3 Load test

Extensión de `scripts/load_test_synthetic.py`: 35 alumnos × 20 preguntas × fotos sintéticas (renders de LaTeX a imagen con ruido). Mide p95 end-to-end, queue depth, costo total, DLQ count.

### A9.4 Métricas CloudWatch nuevas

`guides.ingest_cost_usd`, `guides.extraction_failed_count`, `solution_gen.needs_review_ratio`, `grading.cost_per_submission`, `grading.cache_hit_rate`, `grading.unaligned_rate`, `grading.illegible_rate`.

---

## Track paralelo v8 (corre en todos los sprints, ~20% de capacidad)

1. **`scripts/error_catalog_generator.py` formal** (plan v8 A2 sin cambios de diseño): 5 lotes de ~440 entries, dominio por dominio, **priorizando los dominios observados en las guías golden de M23 y del piloto**. Dedupe (`error_catalog_dedupe.py`) + finalize → el backend importa un lote por sprint (S11-S15).
2. **`prompts/by_domain/*.py`:** materializar los 19 prompts (deuda A4 v8). ⚠️ Parte de este trabajo existe sin commitear en `feature/assignment` — **verificar el working tree antes de re-escribir**.
3. **Datos golden para strategies del backend:** attempts sintéticos por subdominio nuevo (4 por sprint, coordinado con el addendum backend S11-S15).

---

## Subdirectorios nuevos en este repo

```
innova-ai-engine/
├── src/
│   ├── guide_ingest/          (NUEVO — A6: precheck, extractor, chunk merger, tex renderer, schemas)
│   ├── solution_gen/          (NUEVO — A7: generator, topic classifier, modos VALIDATE/DERIVE/FULL)
│   ├── submission_grader/     (NUEVO — A8: grader, alignment schemas, cheap mode)
│   └── pipeline/
│       ├── guide_ingest_worker.py    (NUEVO)
│       ├── solution_generator.py     (NUEVO)
│       ├── submission_grader.py      (NUEVO)
│       └── hourly_alerts.py          (NUEVO — deuda v7, sprint A9)
├── prompts/
│   ├── guide_ingest/extract_guide.py     (NUEVO, versionado)
│   ├── solution_gen/generate_solution.py (NUEVO, versionado)
│   ├── grading/transcribe_and_align.py   (NUEVO, versionado)
│   └── by_domain/                        (track paralelo — 19 archivos)
└── scripts/
    ├── grading_eval.py                   (NUEVO — A9)
    └── error_catalog_generator.py        (track paralelo, formalización)
```

---

## Settings nuevos (`src/shared/settings.py`)

```python
sqs_guide_ingest_url: str
sqs_solution_gen_url: str
sqs_submission_grade_url: str
s3_guides_bucket: str
s3_submissions_bucket: str
ssm_guides_ingest_paused_param: str = "/innova/guides/ingest_paused"
ssm_guides_grading_paused_param: str = "/innova/guides/grading_paused"
ssm_guides_cheap_mode_param: str = "/innova/guides/grading_cheap_mode"
solution_gen_use_batches: bool = True
guide_ingest_chunk_pages: int = 20
grading_min_transcription_confidence: float = 0.5
```

---

## Costos one-time v9 (este repo)

| Item | Costo |
|---|---|
| Iteración de prompts sobre golden sets (extracción + pauta + grading, ~3 rondas) | ~$30 |
| Catálogo 341→2400 (ya presupuestado en v8) | ~$50 |
| **Total setup v9** | **~$80 one-time** |

---

## Backlog técnico v9

- [ ] Async Gemini (`generate_content_async`) — arrastrado de v7.
- [ ] Property-based tests BKT con Hypothesis — arrastrado de v7.
- [ ] Cobertura ≥75% en `src/` incluyendo los 3 paquetes nuevos.
- [ ] Supabase Realtime para estado de Guide/Submission (post-MVP; polling en MVP).
