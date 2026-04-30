# Requirements — Innova EdTech (Post-Pivot)

> Versión 2.0 · 2026-04-29

## Requerimientos Funcionales (RF)

### RF-1: Practica matemática con detección de errores
- **RF-1.1** El alumno puede resolver ejercicios matemáticos paso a paso vía componente `math-input`.
- **RF-1.2** El sistema valida la respuesta y clasifica el error con un `error_type` específico (no solo "está mal").
- **RF-1.3** El sistema entrega feedback inmediato al alumno con explicación del error (`error-renderer`).
- **RF-1.4** El sistema soporta upload de fotos de cuaderno; la imagen se procesa vía OCR Vision (Gemini Flash) → JSON estructurado → rule engine.

### RF-2: Tracking de dominio (Mastery)
- **RF-2.1** El sistema mantiene `p_known` por (alumno, skill) actualizado en tiempo real con BKT.
- **RF-2.2** El sistema clasifica al alumno en niveles `AT_RISK`, `STRUGGLING`, `PROFICIENT`, `MASTERED` por skill.
- **RF-2.3** El sistema detecta drops (caídas de 2+ niveles en 7 días) automáticamente.

### RF-3: Dashboard del profesor
- **RF-3.1** El profesor accede a su dashboard vía login Cognito.
- **RF-3.2** El profesor ve alertas activas: `AT_RISK_SKILL`, `COMMON_ERROR_DETECTED`, `STUDENT_DROP`.
- **RF-3.3** El profesor ve heatmap de mastery por skill × alumno del classroom.
- **RF-3.4** El profesor ve frecuencia de errores comunes en el classroom (top 5).
- **RF-3.5** El profesor puede asignar manualmente práctica focalizada.

### RF-4: Asignación automática de práctica
- **RF-4.1** Cuando un alumno cae en `AT_RISK` en un skill, el sistema genera automáticamente un `PracticeAssignment` con 5 items focalizados.
- **RF-4.2** La selección de items usa Fisher information de IRT (item óptimo dado mastery actual).
- **RF-4.3** El apoderado vinculado recibe notificación push (Expo) con la asignación.

### RF-5: Onboarding y administración
- **RF-5.1** Admin de colegio crea classrooms con profesor asignado.
- **RF-5.2** Profesor agrega alumnos vía email (envía link Cognito signup).
- **RF-5.3** Padre se vincula a alumno vía código de invitación generado por el alumno.

## Requerimientos No Funcionales (NFR)

### NFR-1: Performance
- **NFR-1.1** Latencia rule-engine classification: <100ms p95.
- **NFR-1.2** Latencia attempt submission end-to-end: <500ms p95.
- **NFR-1.3** Latencia OCR Vision: <5s p95 async.
- **NFR-1.4** Latencia LLM async classification: <5min desde attempt hasta dashboard.
- **NFR-1.5** Lambda cold start backend: <2s.

### NFR-2: Disponibilidad
- **NFR-2.1** Uptime objetivo entrega 4: 99% mensual (8h downtime aceptable en pilot).
- **NFR-2.2** RTO < 4h, RPO < 1h vía Postgres point-in-time-restore.

### NFR-3: Costo
- **NFR-3.1** Coste pilot (5 alumnos): ≤ $5/mes total.
- **NFR-3.2** Coste a 1000 alumnos: ≤ $300/mes total.
- **NFR-3.3** Killswitch automático si LLM mensual > $80 USD.
- **NFR-3.4** Killswitch automático si OCR mensual > $50 USD.

### NFR-4: Seguridad y privacidad
- **NFR-4.1** Compliance con Ley 21.180 (Chile) sobre datos NNA.
- **NFR-4.2** Compliance con COPPA (US, exportabilidad futura).
- **NFR-4.3** Cero PII en logs de telemetría o LLM/OCR calls.
- **NFR-4.4** Imágenes upload purgadas a 30 días (S3 lifecycle).
- **NFR-4.5** Consentimiento parental registrado antes de habilitar uploads.
- **NFR-4.6** Cognito MFA obligatorio para profesores y admins.
- **NFR-4.7** Secrets en AWS Secrets Manager, NUNCA en código.

### NFR-5: Calidad de software
- **NFR-5.1** Coverage tests unit + integration ≥75% en cada repo.
- **NFR-5.2** E2E tests críticos green en CI antes de merge.
- **NFR-5.3** Branch `main` protegido: 2 reviewers + CI green obligatorios.
- **NFR-5.4** Conventional Commits enforced.
- **NFR-5.5** Linear history (squash-merge), no merge commits.
- **NFR-5.6** TypeScript strict mode (no `any`), Python pyright strict mode (no `Any`).

### NFR-6: Observabilidad
- **NFR-6.1** Structured logging JSON con `trace_id` propagated end-to-end.
- **NFR-6.2** CloudWatch dashboards: cost, errors, latency, queue depth.
- **NFR-6.3** Sentry integration en frontend (no PII).
- **NFR-6.4** AI usage logs: cada interacción significativa documentada en `docs/ai-logs/<usuario>/`.

### NFR-7: Escalabilidad
- **NFR-7.1** Arquitectura debe escalar linealmente hasta 10K alumnos sin cambios.
- **NFR-7.2** Sin cuellos de botella síncronos: todo procesamiento pesado vía SQS.
- **NFR-7.3** Stateless Lambdas: estado solo en Postgres, Mongo, S3.

### NFR-8: Internacionalización
- **NFR-8.1** Primer idioma: español Chile (es-CL).
- **NFR-8.2** UI debe soportar agregar idiomas via i18n keys (i18next o equivalente).

### NFR-9: Accesibilidad
- **NFR-9.1** WCAG 2.1 AA compliance en `apps/practice` y `apps/teacher`.
- **NFR-9.2** Componente `math-input` accesible vía teclado completo.
- **NFR-9.3** Soporte screen-readers (ARIA labels en todos los inputs matemáticos).

## Restricciones

- **R-1** Stack obligatorio: NestJS + TypeScript + Python 3.11 + AWS Serverless + Anthropic + Gemini.
- **R-2** Modal.com OUT del MVP (reservado a post-pivot fine-tuning).
- **R-3** Solo Anthropic API key organizacional (NO personal de ningún miembro).
- **R-4** Hardware local de desarrollo: GTX 1650 Ti 4GB VRAM máximo. NO entrenar modelos pesados localmente.
- **R-5** Plazos rígidos: 3 May, 7 Jun, 19 Jun. NO se mueven.
- **R-6** Piloto: 1 colegio, 1 curso, ≤20 alumnos, ~5 testeando activamente.
- **R-7** Idioma documentación: español. Idioma código: inglés.

## Métricas de éxito (medibles)

| Métrica | Meta entrega 2 (3 May) | Meta entrega 3 (7 Jun) | Meta entrega 4 (19 Jun) |
|---------|------------------------|------------------------|-------------------------|
| Topics implementados | 1 (subtraction_borrow) | 3 | 5 |
| Error_types con rule engine | 8 | 18 | 30 |
| Coverage tests | informativo | ≥75% | ≥75% |
| Uptime piloto | demo only | 95% | 99% |
| Alumnos activos en piloto | 5 (entrevistas) | 5–10 | 15–20 |
| Profes en dashboard | 1 (demo) | 1–2 | 3 |
| NPS profesor | n/a | ≥30 | ≥40 |
| Coste mensual | $0 | <$5 | <$15 |
| % UNCLASSIFIED post rule engine | n/a (no LLM) | <30% | <20% |
