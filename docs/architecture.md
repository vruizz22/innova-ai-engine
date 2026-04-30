# Architecture Decision Records (ADRs)

> Innova EdTech · post-pivot · 2026-04-29

Cada ADR documenta una decisión arquitectónica relevante con su contexto, opciones consideradas, decisión y trade-offs. Formato Michael Nygard simplificado.

---

## ADR-001: Pivot de FSLSM a detección de errores procedurales en matemáticas

**Estado:** Accepted (2026-04-29)
**Contexto:** El enfoque original (perfilamiento FSLSM via SVM/DQN sobre minijuegos) tenía 3 problemas críticos:
1. Supuesto pedagógico desacreditado (Pashler 2008, "Learning Styles: Concepts and Evidence").
2. Sin datos reales — bootstrap sintético con thresholds inventados → modelos overfitean al diseño, no al mundo.
3. Profesores chilenos en 20 entrevistas no compraron "perfilamiento cognitivo" — pidieron "saber QUÉ error está cometiendo el alumno antes de la prueba".

**Decisión:** Pivot a detección de errores procedurales en matemáticas (3°–6° básico) con stack híbrido Rules Engine + BKT + IRT + LLM async.

**Consecuencias:**
- ✅ Base científica sólida: Brown-VanLehn 1980 (rules), Corbett-Anderson 1995 (BKT), Lord 1980 (IRT) — todas con 30+ años de validación.
- ✅ Time to MVP: 4 días (vs ~10 semanas estimadas para FSLSM).
- ✅ Coste 5x más alto que estimación FSLSM optimista, pero 100x más confiable.
- ❌ Requiere descartar la mayoría del trabajo previo en `innova-ai-engine`.
- ❌ Cliente potencial debe entender "errores procedurales" — vocabulario nuevo a vender.

**Tradeoff aceptado:** descartar 6 semanas de trabajo previo a cambio de un producto vendible con base científica defendible.

---

## ADR-002: Drop Modal.com del MVP

**Estado:** Accepted (2026-04-29)
**Contexto:** Modal.com fue pieza central del stack original para training GPU on-demand de SVM/DQN. Post-pivot, ya no entrenamos modelos de deep learning.
**Opciones:**
- A) Mantener Modal por si lo necesitamos luego.
- B) Eliminar Modal del MVP, reintroducir solo si datos lo justifican post-pivot.
**Decisión:** B. BKT/IRT son closed-form (no GPU). LLM va vía Anthropic API (no hospedamos). No hay fundamentación técnica para Modal en MVP.
**Consecuencias:**
- ✅ Ahorro $0–30/mes.
- ✅ Una dependencia menos.
- ✅ Stack más simple para nuevos developers.
- ⏳ Ticket guardado: si acumulamos >100K attempts y queremos fine-tunear distil propio, Modal es la primera opción de exploración.

---

## ADR-003: Neon Postgres serverless > Aurora Serverless v2

**Estado:** Accepted (2026-04-29)
**Contexto:** Aurora Serverless v2 cuesta ~$36/mes mínimo (0.5 ACU sin pause). Neon free tier ofrece 0.5GB + 191 compute hours/mes con auto-suspend.
**Opciones:**
- A) Aurora Serverless v2 — más madurez, integración AWS.
- B) Neon Postgres — free tier, auto-suspend, pero cold-start ~3s.
- C) Self-host Postgres en EC2 — barato pero ops overhead.
**Decisión:** B (Neon) hasta superar 500 colegios o requerir SLA 99.95%. Migrar a Aurora cuando justifiquen costos.
**Consecuencias:**
- ✅ $0 fixed durante piloto + early growth.
- ✅ Branching de DB para staging gratis.
- ❌ Cold-start ~3s afecta primer attempt del día. Mitigado: warmer Lambda cron cada 4 min en horas pico.

---

## ADR-004: Gemini 2.0 Flash > Mathpix > Claude Vision para OCR

**Estado:** Accepted (2026-04-29)
**Contexto:** Necesitamos OCR de matemáticas manuscritas (cuadernos escolares). Mathpix es state-of-art pero requiere $19.99 setup fee + $29 deposit — incompatible con MVP lean.
**Opciones evaluadas:**

| Opción | Costo piloto | Costo escala 1K | Accuracy | Setup |
|--------|--------------|------------------|----------|-------|
| Mathpix Convert | $48.99 setup + ~$200/mes | $200/mes | Excelente | Requiere business account |
| AWS Textract | $5/mes | $1000/mes | Pobre en math | Inmediato |
| Claude Haiku Vision | $5/mes | $1000/mes | Muy buena | Inmediato |
| **Gemini 2.0 Flash** | $0 (free tier) | $99/mes | Buena | Inmediato |
| LaTeX-OCR self-hosted | $30/mes EC2 | $30/mes | Buena | GPU req'd |

**Decisión:** Gemini 2.0 Flash como OCR primario + `MathOCRPort` adapter para fallback opcional a Claude Vision o LaTeX-OCR self-hosted post-pivot.

**Consecuencias:**
- ✅ Free tier cubre piloto completo a $0.
- ✅ 10x más barato que Claude Vision a escala.
- ✅ Adapter pattern preserva opcionalidad arquitectónica.
- ❌ Dependencia de Google Cloud (single-vendor risk). Mitigado: adapter swappeable en horas.
- ❌ Free tier limit (15 RPM, 1M TPM): puede saturarse a >50 alumnos concurrentes. Mitigado: paid tier sigue siendo el más barato.

---

## ADR-005: LLM async batched > LLM real-time per attempt

**Estado:** Accepted (2026-04-29)
**Contexto:** El LLM (Capa 4) clasifica los attempts que el rule engine deja como UNCLASSIFIED (~15-30%). Latencia y costo varían dramáticamente según approach.
**Opciones:**
- A) LLM síncrono per attempt: 800ms latencia, $0.40/1K attempts (sin caching).
- B) LLM batch async (20× con prompt caching): 5min latencia, $0.06/1K attempts.
- C) Self-hosted small model (Phi-3.5, Llama 8B): 2s latencia, $0.10/1K, 75% accuracy (peor).
**Decisión:** B. La latencia 5min es tolerable porque el profesor consulta el dashboard al día siguiente, no en tiempo real. Caching agresivo + batching reduce 7x el costo.
**Consecuencias:**
- ✅ 7x más barato que A.
- ✅ Coste viable a escala.
- ❌ Profe NO ve el error específico inmediatamente — solo "está mal". Mitigado: rule engine cubre 70-85% real-time; el 15-30% restante aparece en dashboard async.

---

## ADR-006: BKT closed-form > Deep Knowledge Tracing (DKT/LSTM)

**Estado:** Accepted (2026-04-29)
**Contexto:** BKT (1995) y DKT (Piech 2015) son los dos approaches dominantes para mastery tracking.
**Opciones:**
- A) BKT (4 parámetros, closed-form bayesiano).
- B) DKT (LSTM neural).
- C) BKT-DKT híbrido (Yudelson 2013).
**Decisión:** A.
**Consecuencias:**
- ✅ BKT funciona con 50 attempts por skill (DKT necesita 100K+).
- ✅ Interpretable (4 parámetros con semántica). DKT es black-box.
- ✅ Update closed-form: <5ms en Node.js Lambda.
- ❌ Asume independencia entre skills. Mitigado: prerequisitos modelados explícitamente en `Skill.prerequisites`.
- ⏳ Migrar a BKT-DKT híbrido o DKT puro post-pivot cuando datos lo justifiquen.

---

## ADR-007: Ruta de input dual: digital + photo upload

**Estado:** Accepted (2026-04-29)
**Contexto:** Los niños chilenos hacen matemáticas a mano en cuadernos. Forzar digital input pierde adopción. Pero permitir SOLO upload de fotos pierde la inmediatez del feedback.
**Decisión:** Soportar ambos modos. `apps/practice` ofrece dos botones: "Resolver aquí" (digital) o "Subir foto" (OCR). El backend procesa ambos por el mismo pipeline post-rawSteps.
**Consecuencias:**
- ✅ Adopción mayor — el alumno elige el modo cómodo.
- ✅ El profe puede pedir "resuelve esto en cuaderno y sube foto" — preserva escritura manual.
- ❌ Mantener dos paths frontend duplica QA. Mitigado: backend único, telemetry packages compartidos.
- ❌ OCR latencia ~5s vs digital instantáneo. Aceptable porque feedback async via dashboard.

---

## ADR-008: Trunk-based con 2 reviewers > Gitflow

**Estado:** Accepted (2026-04-29)
**Contexto:** El equipo es de 5 personas con plazos rígidos. Gitflow (develop/release/feature/hotfix) es overkill.
**Decisión:** Trunk-based development sobre `main` protegido. Branches `feat/<issue>-<short-desc>` cortas, PRs <500 líneas, squash-merge, 2 reviewers obligatorios.
**Consecuencias:**
- ✅ Simplicidad operativa.
- ✅ Detección temprana de conflictos.
- ✅ Deploy continuo a producción desde main.
- ❌ Requiere disciplina en feature flags para work-in-progress. Mitigado: en MVP no necesitamos feature flags; todo lo que se mergea es shippeable.

---

## ADR-009: Anthropic Claude Haiku 4.5 (no Sonnet/Opus) para classification

**Estado:** Accepted (2026-04-29)
**Contexto:** Tres tiers Anthropic: Haiku ($1/M input cached, $4/M output), Sonnet ($3/$15), Opus ($15/$75).
**Decisión:** Claude Haiku 4.5 como default. Sonnet 4.6 como fallback para attempts donde Haiku confidence <0.7 (~5% del volumen).
**Consecuencias:**
- ✅ 15x más barato que Sonnet, 75x más barato que Opus.
- ✅ Latencia <2s.
- ❌ Accuracy ~5% inferior a Sonnet (esperado). Mitigado por fallback escalation.
- ⏳ Re-evaluar cada 3 meses cuando Anthropic baja precios o lanza modelos nuevos.

---

## ADR-010: Idioma — código en inglés, docs en español, UI en español Chile

**Estado:** Accepted (2026-04-29)
**Contexto:** Equipo es chileno, cliente es chileno. Pero código eventualmente expuesto a developers internacionales (incubadora, contrataciones).
**Decisión:** Código + commit messages + variables + APIs en inglés. Documentación interna + READMEs (en español-Chile, excepto los repos con `README.md` en inglés para discoverability internacional). UI en es-CL primary, i18n keys preparadas para expansión.
**Consecuencias:**
- ✅ Código auditable por reviewers globales.
- ✅ Onboarding internacional posible.
- ❌ Doble idioma en repos (commits/code en inglés, docs en español). Aceptable.
