# PLAN v7 — Addendum innova-ai-engine

> Acciones concretas. Referencia principal: `../../docs/MASTER_PLAN_v7.md`.
> **Regla #0:** el agente NO ejecuta `uv sync/add`, `serverless deploy`, `pytest --cov`. Los entrega para que Victor los corra. Ver `CLAUDE.md §0`.

---

## Sprint S1 (M7 — bloqueadores B2 + B3)

### B2: rename `AWS_REGION` → `APP_AWS_REGION`

1. Editar `serverless.yml`:
   ```yaml
   provider:
     environment:
       APP_AWS_REGION: ${env:APP_AWS_REGION, 'us-east-1'}
       # eliminar la línea AWS_REGION
   ```
2. Editar `src/shared/settings.py`:
   ```python
   app_aws_region: str = "us-east-1"
   # reemplazar uso de os.environ['AWS_REGION'] por settings.app_aws_region
   ```
3. Actualizar `.env.example` y `.env`.
4. Grep para detectar uso restante: `grep -rn "AWS_REGION" src/`.

### B3: crear colas SQS + secrets

Comandos para Victor (AWS console o CLI):
```bash
aws sqs create-queue --queue-name innova-llm-classify-queue          --region us-east-1
aws sqs create-queue --queue-name innova-ocr-queue                   --region us-east-1
aws sqs create-queue --queue-name innova-attempt-reprocess-queue     --region us-east-1
aws sqs create-queue --queue-name innova-llm-classify-queue-dlq      --region us-east-1
aws sqs create-queue --queue-name innova-ocr-queue-dlq               --region us-east-1
aws sqs create-queue --queue-name innova-attempt-reprocess-queue-dlq --region us-east-1
```
Luego configurar redrive policy (`maxReceiveCount=5`) en cada cola principal hacia su DLQ.

Agregar ARNs como GitHub Secrets en `innova-ai-engine` y `innova-backend-serverless`:
- `SQS_LLM_CLASSIFY_ARN`
- `SQS_OCR_QUEUE_ARN`
- `SQS_ATTEMPT_REPROCESS_ARN` (nueva v7)

**DoD:** `serverless deploy --stage prod` corre sin `Reserved keys: AWS_REGION` y sin `Unresolved variable: ${env:SQS_*_ARN}`.

---

## Sprint S2 (M10 — curriculum loader)

1. Crear `scripts/curriculum_loader.py`:
   - Lee `/home/vruizz22/repositorios/innova/{3ero,4to,5to,6to}.txt`.
   - Parsea estructura: `# Unidad N: ...`, `## Tema: ...`, lista de subtemas/objetivos.
   - Emite `curriculum.json`:
     ```json
     {
       "subject": "matematica",
       "language": "es",
       "grades": [
         { "level": 3, "units": [
           { "name": "Números naturales", "topics": [
             { "name": "Comparación de números", "prerequisites": [], "objectives": [...] }
           ]}
         ]}
       ]
     }
     ```
2. Output va a `innova-backend-serverless/prisma/seeds/data/curriculum-matematica-basica.json` (commiteado).
3. Script idempotente: si el JSON ya existe y los `.txt` no cambiaron (hash), no-op.
4. Tests: `tests/scripts/test_curriculum_loader.py` con fixtures pequeños.

Comando Victor:
```bash
cd innova-ai-engine
uv run python scripts/curriculum_loader.py \
  --input-dir ../ \
  --output ../innova-backend-serverless/prisma/seeds/data/curriculum-matematica-basica.json
```

**DoD:** JSON generado consumido por seeds Prisma sin errores.

---

## Sprint S3 (M11 — Alert Generator + OCR loop)

### Alert Generator

1. `src/pipeline/hourly_alerts.py`:
   ```python
   from __future__ import annotations
   from typing import Any
   import structlog

   from src.shared import postgres
   from src.alerts.detector import detect_alerts

   logger = structlog.get_logger(__name__)

   async def _run() -> dict[str, int]:
       async with postgres.acquire() as conn:
           rows = await conn.fetch("""
               select stm.student_id, stm.topic_id, stm.p_known, stm.trend_7d,
                      e.course_id, ct.teacher_id, t.unit_id
               from student_topic_mastery stm
               join enrollment e        on e.student_id = stm.student_id
               join course_teacher ct   on ct.course_id = e.course_id
               join topic t             on t.id = stm.topic_id
               where stm.last_attempt_at > now() - interval '7 days'
           """)
           alerts = detect_alerts(rows)
           await postgres.bulk_insert_alerts(conn, alerts)
       return {"alerts_created": len(alerts)}

   def handler(event: dict[str, object], context: object) -> dict[str, object]:
       import asyncio
       return asyncio.run(_run())
   ```
2. `src/alerts/detector.py` — lógica pura:
   - `AT_RISK_STUDENT`: `p_known < 0.4` en ≥2 topics activos del curso.
   - `COMMON_ERROR_IN_TOPIC`: ≥50% alumnos curso mismo `error_type` ult. 7 días en topic.
   - `STUDENT_DROP`: sin intentos en 3 días.
   - `UNIT_OFF_TRACK`: avg `p_known` del curso en unit activa < 0.3.
   - Dedup por `(teacher_id, alert_type, topic_id, student_id, date)`.
3. `serverless.yml`:
   ```yaml
   functions:
     hourlyAlerts:
       handler: src.pipeline.hourly_alerts.handler
       events:
         - schedule: cron(0 * * * ? *)
       timeout: 300
       memorySize: 1024
   ```
4. Tests con Hypothesis: invarianzas (sin alertas duplicadas, payload bien formado).

### OCR feedback loop

1. Editar `src/pipeline/ocr_worker.py`:
   - Post-extracción, en lugar de actualizar Postgres, publicar a SQS `attempt-reprocess-queue`:
     ```python
     await sqs.send_message(
         queue_url=settings.sqs_attempt_reprocess_url,
         body=json.dumps({
             "attempt_id": attempt_id,
             "latex_steps": result.latex_steps,
             "provider": result.provider.value,
             "confidence": result.overall_confidence,
         }),
         message_attributes={"trace_id": {"StringValue": trace_id, "DataType": "String"}},
     )
     ```
2. Si `confidence < 0.5`: en vez de reprocess queue, publicar a `low-confidence-review-queue` (nueva, opcional, para revisión humana profe).
3. El consumer vive en backend (`AttemptReprocessWorker`, ver addendum backend S5).

**DoD:** alerta generada por Alert Generator visible en `TeacherAlert` <1h post-intento. Foto alumno → backend re-clasifica <2 min.

---

## Sprint S4 (post-piloto — optimizaciones)

- [ ] Async Gemini: cambiar `gemini_adapter.py` a `genai.models.generate_content_async()`.
- [ ] Property-based BKT tests con `hypothesis`:
  - `p_known ∈ [0,1]` invariante.
  - Monotonicidad: respuestas correctas consecutivas → `p_known` no decrece.
  - Idempotencia parcial.
- [ ] Recovery test IRT: generar 1000 datos sintéticos 2PL, verificar `|a_recovered - a_true| < 0.2` en p90.
- [ ] CI GitHub Actions:
  ```yaml
  - run: uv run pyright src/
  - run: uv run ruff check src/ tests/
  - run: uv run pytest --cov=src --cov-fail-under=75
  ```

---

## Tabla rápida de handlers Lambda v7

| Handler | Trigger | Memory | Timeout | Estado |
|---|---|---|---|---|
| `health` | API GW | 256 | 30s | ✅ |
| `llmClassifier` | SQS llm-classify-queue | 512 | 300s | ✅ |
| `ocrWorker` | S3 uploads/* | 1024 | 60s | ⚠️ falta publish reprocess |
| `nightlyBkt` | cron(0 7 * * ? *) | 1024 | 900s | ✅ |
| `nightlyIrt` | cron(15 7 * * ? *) | 1024 | 900s | ✅ |
| `hourlyAlerts` | cron(0 * * * ? *) | 1024 | 300s | ❌ M11 |

---

## Drawio updates pendientes

- `01-high-level-architecture.drawio` — mover adapters Gemini/Claude Vision/Anthropic del container backend al container ai-engine. Lo redibuja Victor con MCP drawio usando `01-how-to-draw-high-level-architecture.md`.
- `02-telemetry-ingestion-pipeline.drawio` — agregar arrow OCR Worker → `attempt-reprocess-queue` → Attempts Controller.
- **Nuevo** `04-domain-model.drawio` — ER del modelo v7 (§4 master plan).
- **Nuevo** `05-alert-and-recommender-pipeline.drawio` — Layer 3 Recommender (backend) + Layer 4 Alert Generator (ai-engine).
