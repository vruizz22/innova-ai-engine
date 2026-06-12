# AI Usage Log — innova-ai-engine

## Session: 2026-06-09 — LLM classifier v8 (by_domain prompts + domain_id grouper)

**Goal:** Activate the v8 error catalog at runtime via the LLM for UNCLASSIFIED
attempts (ADR A4 / ADR-114). Build per-domain prompts + the `domain_id` grouper in
the SQS worker. Also unblock the 2 final backend v8 commands (DRAFT→ACTIVE + codegen).

**Prompt (resumen):** "construir los prompts por dominio (by_domain, ADR-114) + el
agrupador domain_id en el worker, para que el catálogo se use vía LLM en los
UNCLASSIFIED" + desbloquear el `psql` que fallaba con `database "vruizz22" does not exist`.

### Output / cambios

Nuevo y modificado en `src/llm_classifier/` y `src/pipeline/`:

- **`catalog.py` (NUEVO)** — `DomainCatalog` (pydantic), `fetch_domain_catalog(conn, domain_id)`
  resuelve el catálogo ACTIVE de un dominio (JOIN `error_tags`×`domains`, index
  `[domain_id, status]`), `get_domain_catalog` con cache TTL 1h en proceso. `Fetcher`
  Protocol para tipar el conn de asyncpg (untyped upstream). `SPECIAL_ERROR_TYPES =
  CORRECT / UNCLASSIFIED / TRANSVERSAL_LIKELY`.
- **`prompts.py`** — registry `DOMAIN_SPECS` (17 dominios reales) + `build_domain_system_prompt`.
  El catálogo NO se hardcodea: se inyecta en runtime desde DB (`taxonomy_text`).
- **`tools.py`** — `build_classify_tool(error_codes)`: enum del tool = catálogo del
  dominio + valores especiales (mantiene al modelo en códigos `ErrorTag` reales → FK resuelve).
- **`client.py`** — `classify_batch_for_domain(attempts, catalog)`; refactor de helpers
  compartidos (`_ensure_not_paused`, `_user_payload`, `_invoke`). Fix de bug latente:
  `settings.aws_region` → `app_aws_region` (el killswitch SSM estaba anulado en silencio).
- **`schemas.py`** — `Attempt` ahora acepta `domain_id` + `subdomain_code` (opcionales, back-compat v7).
- **`pipeline/llm_consumer.py`** — agrupa por `domain_id`, clasifica un grupo por dominio
  (by_domain; fallback v7 genérico si no hay catálogo), y **corrige el write a v8**: la tabla
  `attempts` no tiene `error_type`/`llm_evidence`; resuelve el code → `error_tag_id` (FK) vía
  subquery (`CORRECT/UNCLASSIFIED/TRANSVERSAL_LIKELY` → NULL), `classifier_source='LLM'`.
- Tests: `test_catalog.py` (NUEVO) + extensión de `test_prompts/test_tools/test_client/test_llm_consumer`.
  **26 passed.** ruff clean, pyright strict 0 errores.

### Decisiones / desviaciones del plan

1. **Registry en vez de 18 archivos `prompts/by_domain/<code>.py`.** El único delta por dominio
   es el header de especialización; el catálogo es DATA inyectada desde DB. Un registry
   (`DOMAIN_SPECS`) cachea igual por `domain_code + catalog_hash` y evita 18 archivos casi
   idénticos. Comportamiento idéntico al ADR, menos duplicación.
2. **17 dominios, no 18.** El catálogo/DB tiene `ALGEBRA` como único dominio (el ADR lo
   dividía en `algebra_linear`/`algebra_quad`).
3. **El fetch del catálogo vive en el consumer async (asyncpg), no en `client.py`.** CLAUDE.md §10
   prohíbe DB síncrona; `client.py` es sync (SDK Anthropic sync). El consumer hace el fetch
   (cache 1h) y lo inyecta. Realiza la intención del ADR A4.2 respetando §10.
4. **Write corregido a schema v8** (`error_tag_id` FK, no `error_type`). El consumer v7 escribía
   columnas inexistentes → el path LLM v8 estaba muerto en el write. Ahora resuelve code→FK.
5. **TRANSVERSAL_LIKELY**: enum + prompt lo soportan; el segundo pase con re-encolado a TRANSV
   (ADR A4.4) queda como follow-up (requiere productor SQS en el consumer).

### Blocker backend desbloqueado

`psql "$DATABASE_URL"` fallaba porque `$DATABASE_URL` estaba **vacío** en el shell interactivo
(vive en `.env`, lo carga Node/Prisma, no zsh). DB real: puerto 5433, `innova_dev_db`, user
`postgres`. Comandos correctos entregados a Victor (docker exec / host psql + `pnpm codegen:error-tags`).

---

## Session: 2026-06-09 — Catálogo: profundización batch 1 (ARITH/FRACT/DEC/ALGEBRA)

**Prompt:** "Profundizar el catálogo — más entries por dominio hacia ≥2540, priorizando
ARITH/FRACT/ALGEBRA/DEC. Mismo flujo de import ya validado."

**Output:** `scripts/catalog_depth_batch_2026_06_09.py` autorea **71 entries nuevas**
(ARITH +22, FRACT +18, DEC +15, ALGEBRA +16), source `LLM_GENERATED`, status `DRAFT`,
mismo schema/estilo (español, referencias reales: Mack, Behr et al., Brown & VanLehn,
Küchemann, Clement, Collis, Gelman & Gallistel). El script valida JSON + unicidad de
`code` (global) antes de anexar a `out/catalog/*.jsonl`. Autoreadas vía suscripción Claude
Code ($0), no API key.

- Catálogo: **253 → 324 entries**, 0 duplicados, 0 problemas de schema.
- Regenerado el combinado plano `out/error_catalog.jsonl` (324) desde los 17 numerados
  (el import lee ese archivo, no la carpeta). Delta verificado: +71 / -0.

**Secuencia de import para Victor (orden importa: import RESETea status a DRAFT vía upsert,
por eso el flip va DESPUÉS):**

```bash
cd ~/repositorios/innova/innova-backend-serverless
pnpm import:catalog --input=../innova-ai-engine/out/error_catalog.jsonl     # upsert idempotente
docker exec -i innova-postgres-dev psql -U postgres -d innova_dev_db \
  -c "UPDATE error_tags SET status='ACTIVE' WHERE status='DRAFT';"
pnpm codegen:error-tags
```

**Decisión:** batch acotado y de alta calidad (no relleno masivo). Llegar a ≥2540 es un
esfuerzo multi-batch; este batch 1 deja el flujo de profundización validado end-to-end y
prioriza los 4 dominios pedidos. El resto queda para próximas sesiones (como pidió Victor).

---

## Session: 2026-06-09 — Fix `codegen-error-tags.ts` (backend)

Import (324, +71) y flip DRAFT→ACTIVE (`UPDATE 324`, total ACTIVE 341 = 324 catálogo + 17
tags base) corrieron OK. `pnpm codegen:error-tags` falló con **ENOENT** al escribir
`src/shared/domain/error-tags.generated.ts`. Dos bugs en `scripts/codegen-error-tags.ts`:

1. `fs.writeFileSync` no crea carpetas padre y `src/shared/domain/` no existía →
   agregado `fs.mkdirSync(path.dirname(OUTPUT_PATH), { recursive: true })`.
2. El template emitía `export const enum ErrorTagCode` + `Object.values(ErrorTagCode)`:
   con `isolatedModules: true` (tsconfig) un `const enum` está prohibido y da TS2475 al
   usarlo como valor → cambiado a `enum` normal (string enum: `Object.values` devuelve los
   valores, que es lo que `ALL_ERROR_TAG_CODES` necesita). Verificado: ningún módulo
   consume aún `ErrorTagCode`, sin breakage downstream.

Victor: re-correr `pnpm codegen:error-tags`.
