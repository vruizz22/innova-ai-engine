# Milestones — Sprint Plan

> Trunk-based · 2026-04-29

## Calendario consolidado

```
Abril  29 30 │ Mayo 01 02 03 │ ... 30 │ Junio 01 ... 07 │ ... 19
   M0  ┃ M1 (3 días code) ┃   M2  │     M3 (4 semanas)    │ M4 │  M5    │  M6
       ┃                  ┃ Entrega│                        │ Entr│        │ Entr
       ┃                  ┃   2    │                        │  3  │        │  4
```

## Sprint 0 — Spec & Governance (Mié 29 Abr)

**Duración:** 1 día. **Branch:** `main` directo (M0 es solo docs).

### Deliverables

1. Plan maestro firmado.
2. 10+ archivos `.github/instructions/` reescritos.
3. 4 prompts `docs/prompt/` actualizados.
4. 6 drawios + mermaids actualizados (3 formal + 3 mermaid).
5. 5 governance docs (`roadmap`, `requirements`, `milestones`, `architecture`, `error-taxonomy`).
6. 2 DBMLs reescritos.
7. 3 `CLAUDE.md` por repo + 3 `README.md` por repo.
8. Branch protection rules configuradas en los 3 repos.
9. CODEOWNERS + PR template en cada repo.
10. Anthropic + Gemini API keys cargadas como secrets organizacionales.

### Definition of Done

- [ ] Todos los archivos commit & push a main del repo `innova` (docs).
- [ ] PRs (1 por repo) abiertos en `innova-backend-serverless`, `innova-ai-engine`, `innova-clients` con: README + CLAUDE.md + workflows base + branch protection setup + CODEOWNERS.
- [ ] Slack post equipo con resumen del pivot y links.

## Sprint 1 — MVP minimal end-to-end (Jue 30 Abr — Sáb 2 May)

**Duración:** 3 días. **Scope:** 1 topic, 8 error_types, sin LLM, sin OCR.

### Backend (Victor, Pablo)

| Day | Task |
|-----|------|
| Jue 30 | Prisma schema + migrations + Neon free tier connected |
| Jue 30 | `attempts`, `mastery`, `items`, `skills` modules skeleton |
| Vie 01 | `RuleEngine` + `SubtractionBorrowStrategy` con 8 error_types |
| Vie 01 | `MasteryService.applyAttempt` BKT closed-form |
| Vie 01 | Seed script: 30 items canónicos `subtraction_borrow` |
| Sáb 02 | Endpoints `POST /attempts`, `GET /mastery/:studentId`, `GET /items` working en Lambda dev |

### Frontend (Eitan, Matías, Gabriel)

| Day | Task |
|-----|------|
| Jue 30 | Turborepo init + `apps/practice` + `apps/teacher` skeleton |
| Jue 30 | `packages/math-input` mínimo (column-based) |
| Vie 01 | `apps/practice`: pantalla "resolver problema" + feedback inmediato |
| Vie 01 | `apps/teacher`: pantalla "lista alumnos + mastery + top errors" |
| Sáb 02 | Wire-up real con backend o mock data |

### Integration & Demo (Sáb 2 May)

- Integración E2E real (API real, no mock).
- Script: 5 alumnos sintéticos × 10 attempts → poblar dashboard.
- Demo dry-run interno (3pm).
- Slides entrega 2 finales (8pm).

### Definition of Done

- [ ] Demo en localhost o staging URL funcional.
- [ ] 1 alumno puede resolver 5 problemas y ver errores clasificados.
- [ ] 1 profe puede ver dashboard con 5 alumnos.
- [ ] Slides preparadas.

## Sprint 2 — Entrega 2 + Entrevistas (Dom 3 May)

- Mañana: revisión final + presentación.
- Tarde: 5 entrevistas con MVP en mano.
- Noche: capturar feedback estructurado en `docs/feedback-entrega-2.md`.

## Sprints 3–6 — Hardening + Features (Lun 4 May — Vie 30 May)

**Duración:** 4 semanas. Sprint planning semanal cada lunes.

### Sprint 3 (5–11 May): LLM + OCR foundation

- LLM Classifier: Anthropic SDK + prompt caching + tool_use + SQS consumer.
- OCR Vision: presigned URL + Lambda OCR + Gemini adapter.
- `apps/practice`: agregar `upload-scanner` flow.
- Telemetry buffer 2s flush real.

### Sprint 4 (12–18 May): More topics + nightly batch

- `addition_carry` strategy + 5 error_types.
- `fractions_addsub_same_denom` strategy + 5 error_types.
- BKT nightly calibration Lambda (Python).
- IRT 2PL nightly Lambda (Python).
- Coverage gate ≥75% activado.

### Sprint 5 (19–25 May): Parent app + alerts

- `apps/parent` Expo Android: push notifications + assignment list.
- `PracticeAssignment` flow completo.
- Alert Generator cron Lambda.
- CloudWatch alarms.

### Sprint 6 (26–30 May): Pilot kickoff + observability

- Real pilot starts (1 colegio, 1 curso, 5 alumnos).
- Sentry integration en frontend.
- Performance audit + cold-start optimization.
- Documentation pass.

## Sprint 7 — Entrega 3 (1–7 Jun)

- Pilot data analysis.
- Pricing model documentation.
- Apoderados interviews (≥3).
- Slides entrega 3.

## Sprints 8–10 — Polish + incubator prep (8–18 Jun)

### Sprint 8 (8–11 Jun): Tauri + onboarding

- `apps/desktop` Tauri 2.
- Onboarding flow (school → teacher → student → first session).
- i18n base.

### Sprint 9 (12–15 Jun): More topics + pitch

- `mult_single_digit` + `division_long` strategies.
- Pitch deck draft.
- Financial model spreadsheet.

### Sprint 10 (16–18 Jun): Final polish

- Bug bash.
- Demo rehearsal.
- Pitch deck final.

## Sprint 11 — Entrega 4 (Vie 19 Jun)

- Producto en producción.
- Pitch a panel + incubadora.

## Daily standups

- Hora: 9am, 10 min, async vía Slack thread.
- Format: `[ayer] [hoy] [bloqueos]`.

## Retrospectivas

- Cada domingo 8pm, 30 min.
- Output: 3 things to keep / 3 things to drop / 3 things to try.
- Archivar en `docs/retros/<YYYY-MM-DD>.md`.

## Capacity y owners

| Persona | Capacity (h/sem) | Áreas owned |
|---------|------------------|--------------|
| Victor | 30 | Arquitectura, Backend, AI Engine, lead técnico |
| Pablo | 25 | Backend, DBs |
| Eitan | 25 | Frontend, AI Engine secundario |
| Matías | 20 | Frontend, UX |
| Gabriel | 20 | Frontend, UX |

## Riesgos y planes de contingencia

| Riesgo | Probabilidad | Impacto | Plan B |
|--------|--------------|---------|---------|
| OCR Gemini inadequate accuracy | Media | Alto | Fallback Claude Vision en M3 |
| Anthropic key cost explosion | Baja | Alto | CloudWatch killswitch automático |
| Rule engine coverage <50% real | Media | Medio | Más prompt engineering al LLM, ampliar catálogo |
| Pilot escuela cancela | Media | Alto | Backup escuela conocida (vía Joakim) |
| Cognito setup retraso | Media | Medio | Stub auth para MVP, integrar real en M3 |
| Anyone se enferma <72h entrega | Alta | Alto | Pair programming + redundancia de owners |
