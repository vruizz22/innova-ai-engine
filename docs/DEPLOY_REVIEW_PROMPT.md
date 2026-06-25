# Prompt de auditoría de deploy — innova-ai-engine (para Claude en Google Chrome)

> Pega esto en **Claude con navegación**. Abre cada link y reporta con evidencia. Mucho de esto
> vive en la consola AWS (login requerido): si no puedes entrar, márcalo `NO_VERIFICABLE` y dime
> qué tendría que revisar yo manualmente.

---

## Contexto

Workers ML/AI en **AWS Lambda contenedores** (Serverless v3, Python 3.11). **Event-driven**
(SQS / S3 / EventBridge) — NO es una API pública, así que la verificación es por
GitHub Actions + consola AWS (Lambda / SQS / CloudWatch / EventBridge), no por HTTP.
Deploy **solo en `main`** (`deploy.yml`). **Depende del stack del backend** (que crea las colas).

## Links a revisar

1. `https://github.com/vruizz22/innova-ai-engine/actions`
2. `https://github.com/vruizz22/innova-ai-engine/actions/workflows/deploy.yml`
3. `https://github.com/vruizz22/innova-ai-engine/actions/workflows/ci.yml`
4. Secrets: `https://github.com/vruizz22/innova-ai-engine/settings/secrets/actions`
5. (con login) AWS Console → Lambda, SQS, CloudWatch, EventBridge, región `us-east-1`

## Checklist

### A. Triggers

- [ ] `deploy.yml`: `on.push.branches: [main]` (+ `workflow_dispatch`). Reporta cualquier rama no-main.
- [ ] `ci.yml`: corre en `main`/`feature/**`/`bugfix/**`/PR (eso está OK para CI).

### B. Runs

- [ ] ¿Último `ci.yml` verde? El fallo histórico era `ruff invalid-syntax` (f-string Py3.11) en `src/llm_classifier/client.py`. Si sigue rojo, abre el step y **copia el error**; probablemente el fix no se commiteó.
- [ ] ¿Último `deploy.yml` en `main` verde? El fallo histórico era `Cannot resolve variable ... functions.guideIngest.events.0.sqs.arn`. Si sigue, faltan secrets de ARNs.

### C. Secrets

- [ ] Presencia de: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_ACCOUNT_ID`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DATABASE_URL`, `MONGODB_URI`, `SQS_LLM_CLASSIFY_ARN`, `SQS_OCR_QUEUE_ARN`.
- [ ] **¿Existen los nuevos?** `SQS_GUIDE_INGEST_ARN`, `SQS_SOLUTION_GEN_ARN`, `SQS_SUBMISSION_GRADE_ARN`. Si faltan, ese es el bloqueo del deploy → repórtalo crítico.

### D. AWS (si tienes acceso)

- [ ] Lambda: existen las 8 funciones (`nightlyBkt`, `nightlyIrt`, `llmConsumer`, `ocrWorker`, `guideIngest`, `solutionGenerator`, `submissionGrader`, `hourlyAlerts`) como tipo *Image*.
- [ ] SQS: cada cola tiene su *Lambda trigger* conectado.
- [ ] EventBridge: reglas cron de `nightly_bkt`/`nightly_irt`/`hourly_alerts`.
- [ ] CloudWatch Logs: sin errores repetidos de import / settings (`ANTHROPIC_API_KEY` vacío, `AWS_REGION reserved`, etc.).

## Formato de salida

Tabla **Check | ✅/❌/NO_VERIFICABLE | Evidencia | Acción** + **veredicto**: ¿el ai-engine cumple
"CI verde (f-string fix) + deploy solo main + secrets de ARNs completos + Lambdas con triggers"?
Indica si falta deployar el backend primero.
