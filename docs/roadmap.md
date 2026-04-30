# Roadmap Innova EdTech — Post-Pivot

> Versión: 2.0 · Pivot a detección de errores procedurales en matemáticas
> Última revisión: 2026-04-29

## Hitos del ramo (entregas Innovación UC)

| Fecha | Hito | Estado |
|-------|------|--------|
| **Mié 29 Abr 2026** (hoy) | M0 — Spec & Governance ratificado | 🟡 EN CURSO |
| **Sáb 2 May 2026** | Demo dry-run interno | ⏳ |
| **Dom 3 May 2026** | **Entrega 2 — MVP demoable + entrevistas** | ⏳ |
| **Sáb 7 Jun 2026** | **Entrega 3 — Modelo de negocio + MVP testeado** | ⏳ |
| **Vie 19 Jun 2026** | **Entrega 4 — Producto a incubadora** | ⏳ |

## M0 — Spec & Governance (29 Abril, hoy)

**Objetivo:** dejar 100% documentado el qué, cómo, por qué y costo. Cero código nuevo este día.

- [x] Plan maestro firmado (`/home/vruizz22/.claude/plans/ticklish-hugging-wilkes.md`)
- [x] Reescritura instructions `00–09` + nuevo `04-modelo-cognitivo`, `05-pipeline-bkt-irt`, `06-llm-error-classifier`, `06b-ocr-vision-pipeline`
- [x] Reescritura prompts `01-04` en `docs/prompt/`
- [ ] Drawios `01-03` regenerados (formal XML + mermaid)
- [ ] DBMLs reescritos (`docs/postgresql.dbml`, `docs/mongodb.dbml`)
- [ ] `docs/architecture.md` con ADRs 001-005
- [ ] `docs/error-taxonomy.md` con catálogo MVP (8 errores subtraction_borrow)
- [ ] `docs/requirements.md` y `docs/milestones.md`
- [ ] `CLAUDE.md` por repo (`innova-backend-serverless`, `innova-ai-engine`, `innova-clients`)
- [ ] `README.md` por repo (especialmente backend)
- [ ] Branch protection rules en los 3 repos GitHub (manual)
- [ ] CODEOWNERS file en cada repo
- [ ] Cuenta organizacional Anthropic + key cargada como secret en GitHub

**Owner:** Victor (lead) + revisión rápida del equipo por Slack.

## M1 — MVP Backend + Frontend mínimo (Jue 30 Abr — Sáb 2 May)

**Objetivo:** demo end-to-end con UN solo topic (`subtraction_borrow`), 8 error_types hardcoded, sin LLM, sin OCR, mastery proxy simple.

### Backend (Victor + Pablo)

- [ ] Prisma schema nuevo aplicado, migraciones generadas, Neon free tier conectado.
- [ ] Modules: `attempts`, `mastery`, `items`, `skills`, `auth` (con stub Cognito si tarda).
- [ ] `RuleEngine` con `SubtractionBorrowStrategy` cubriendo 8 error_types.
- [ ] `MasteryService.applyAttempt` con BKT closed-form (parámetros default literatura).
- [ ] Endpoints: `POST /attempts`, `GET /mastery/:studentId`, `GET /items?topic=subtraction_borrow`.
- [ ] Seed script: 30 items canónicos de `subtraction_borrow` (2 y 3 dígitos).
- [ ] CI mínimo: lint + test (sin coverage gate aún).

### Frontend (Eitan + Matías + Gabriel)

- [ ] Turborepo levantado.
- [ ] `apps/practice` Next.js — UN screen: alumno ve problema, escribe respuesta paso a paso, recibe feedback (`isCorrect`, `errorType`).
- [ ] `apps/teacher` Next.js — UN screen: tabla de alumnos con mastery promedio + top 3 errors.
- [ ] `packages/math-input` mínimo (column-based input).
- [ ] `packages/api-client` generado (puede ser hand-rolled en MVP).
- [ ] Mock data si backend no está listo.

### Demo prep (Sáb 2 May)

- [ ] Script de 5 alumnos sintéticos haciendo 10 attempts c/u → poblar dashboard.
- [ ] 2 demos vivos: alumno resuelve correctamente vs alumno comete `BORROW_OMITTED_TENS` → profe ve alerta.
- [ ] Slides para entrega 2.

## M2 — Entrega 2 + Entrevistas (Dom 3 May)

- [ ] Presentación entrega 2 (15 min + Q&A).
- [ ] **5 entrevistas con MVP en mano** (alumnos pruebánolo). Capturar: usabilidad, comprensión del feedback, percepción del profe del dashboard.
- [ ] Bug list y backlog priorizado para M3.

## M3 — Hardening + LLM + OCR + 2 topics más (Lun 4 May — Vie 30 May)

**4 semanas** — la fase larga del proyecto.

- [ ] `LLM Classifier` integrado: SQS standard + Lambda Python + Anthropic Haiku 4.5 con prompt caching.
- [ ] `OCR Vision Pipeline`: presigned-URL upload + Lambda OCR + Gemini 2.0 Flash adapter.
- [ ] Fallback escalation Gemini → Claude Vision implementado.
- [ ] **2 topics nuevos:** `addition_carry` + `fractions_addsub_same_denom`. ~10 nuevos error_types curados.
- [ ] BKT nightly calibration Lambda Python deployed.
- [ ] IRT 2PL nightly Lambda deployed.
- [ ] `apps/parent` Expo app con push notifications básicos.
- [ ] `PracticeAssignment` + parent notification flow completo.
- [ ] Coverage gate ≥75% activado en CI.
- [ ] CloudWatch alarms (LLM cost, OCR cost, DLQ depth, Lambda errors).
- [ ] Branch protection 2-reviewers enforced.
- [ ] `docs/ai-logs/` poblándose por cada miembro.
- [ ] Real pilot starts: 1 colegio, 1 curso, 5 alumnos testeando 4 semanas.

## M4 — Entrega 3: Modelo de negocio + MVP testeado (Sáb 7 Jun)

- [ ] Pricing model documentado (CLP $50K/mes/sala plan estándar).
- [ ] Pilot data analizada: rule engine coverage real medida, mastery deltas, NPS profesor.
- [ ] Entrevistas con apoderados del piloto (≥3).
- [ ] Slides entrega 3.

## M5 — Pulido + Tauri Desktop + Onboarding flow (Lun 9 Jun — Jue 18 Jun)

- [ ] `apps/desktop` Tauri 2 wrapping practice (offline cache).
- [ ] Onboarding flow: alta de colegio → alta de profe → alta de alumnos → primera sesión guiada.
- [ ] Internationalization base (es-CL primary, es-ES fallback).
- [ ] 2 topics adicionales: `mult_single_digit`, `division_long`. ~12 nuevos error_types.
- [ ] Performance audit: cold-start <2s, p95 attempt-classify <100ms.
- [ ] Pitch deck para incubadora (alineado con feedback de pilot).

## M6 — Entrega 4: Producto a incubadora (Vie 19 Jun)

- [ ] Producto demo-ready en producción (innova.cl placeholder).
- [ ] Pitch deck + financial model + traction data del piloto.
- [ ] Roadmap post-incubadora: 5 colegios → 50 colegios → producto vertical SaaS.

## Backlog post-incubadora (NOT in scope para entregas)

- Fine-tuning de modelo distil propio sobre dataset acumulado del piloto.
- Modal.com integrado para training on-demand.
- Apps mobile iOS (Expo).
- Integración con SIE de colegios chilenos (Webclass, Edutech).
- Multi-tenancy + admin de holding educacional.
- Versión inglés para mercado latam.
