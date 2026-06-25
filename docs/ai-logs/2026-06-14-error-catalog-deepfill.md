# AI Usage Log — innova-ai-engine

## Session: 2026-06-14 — Error catalog deep-fill (objetivo ≥2540 superado: 2607)

**Prompt:** "/goal necesito que termines todo de las entries al maximo posible, dejandolas
totalmente integradas, es decir buscar y agregarlas todas mas de las estimadas 2540, mas que
eso de maxima calidad." (Completar TODAS las entries del catálogo `ErrorTag` al máximo, dejarlas
totalmente integradas, superar las 2540 estimadas, con calidad máxima.)

**Output (resumen):**

### 1. Punto de partida y tensión a resolver
- Catálogo previo: 17 archivos `out/catalog/NN-<domain>.jsonl` (G1–G12, MINEDUC FG), combinado en
  `out/error_catalog.jsonl`. Conteo inicial del pase: ~2187 entries.
- Tensión central: **máxima cantidad (>2540) vs. máxima calidad (cero duplicados)**. Los IDs
  estables de los docs `../docs/error-taxonomy/NN-*.md` se solapan semánticamente con el deployed
  pero bajo esquemas de código distintos → volcar todos los IDs de los docs habría creado cientos
  de quasi-duplicados.

### 2. Método deep-fill (por dominio)
1. Dump del deployed por subdominio (Python robusto a espaciado JSON) + lectura del doc del dominio.
2. Diff de conceptos: se añadió **solo el gap-a-target** de conceptos genuinamente nuevos
   (semánticamente distintos), no IDs repetidos bajo otro esquema.
3. Generación con `_data_<domain>_supp.py` (helper `e(...)` → dict del schema) + `_gen_batch.py`
   (dedup por `code` contra TODOS los `[0-9][0-9]-*.jsonl`), luego `validate_catalog.py`.
- Confirmado: INT/DEC ya usaban IDs de los docs (volcado directo de faltantes seguro);
  ARITH/FUNC/TRIG/etc. usaban otros esquemas (requirieron dedup semántico).

### 3. Contrato respetado (schema Zod del importador)
- `code` regex `^[A-Z][A-Z0-9]*_[A-Z][A-Z0-9]*_[A-Z][A-Z0-9_]*$` — **ningún segmento empieza con
  dígito** (corregido `COORD_DIST_3D_FORMULA_FAIL_G11M` → `COORD_DIST_FORMULA_3D_FAIL_G11M`).
- `severity` {LOW,MED,HIGH,CRITICAL}; `source` {CURATED,LLM_GENERATED,FIELD_REPORTED};
  `status` {ACTIVE,DRAFT,DEPRECATED}; `applicable_grades` int 1–12.
- Todas las nuevas: `status=DRAFT`, `source=LLM_GENERATED` (CURATED solo con literatura citada).
- Mapeo grade-hint→grados: G1→[1,2], …, G9M→[9,10], …, G12M→[12].

### 4. Resultado final (validado)
- **2607 entries, 2607 codes únicos, 0 problemas** (`out/catalog/validate_catalog.py`).
- Todos los 17 dominios **≥ target** de `docs/error-taxonomy/README.md §3`. **+67 sobre 2540.**
- Counts: ALGEBRA 380, ARITH 286, FRACT 196, DEC 194, FUNC 180, GEOM 170, POW 160, INT 139,
  TRIG 130, STAT 130, RATIO 112, GEOM3D 110, COORD 100, SEQ 90, LOG 80, TRANSV 80, DATA 70.
- `out/error_catalog.jsonl` regenerado (2607 líneas) con
  `cat out/catalog/[0-9][0-9]-*.jsonl > out/error_catalog.jsonl`.

### 5. Limpieza
- Generadores throwaway `_data_*.py` + `_gen_batch.py` **borrados**. Se conserva
  `validate_catalog.py` (validador reutilizable) y `README.md` (actualizado a 2607 + tabla con Target).

### 6. Costo
- Poblado con la **suscripción Claude Code (Opus 4.8), costo $0** — NO se gastó `ANTHROPIC_API_KEY`.
  Reemplaza el `error_catalog_generator.py` + Opus-vía-API (~$20–50) del plan original.

**Decisión:**
- Catálogo de errores **completo y por sobre objetivo (2607 ≥ 2540)**, 0 inválidas, codes únicos,
  todos los dominios al/por sobre su target. Todas `DRAFT` pendientes de revisión pedagógica.
- **Pendiente Victor** (regla install-by-user, en orden — el importador es create-if-absent y NO
  re-escribe status, por eso el flip DRAFT→ACTIVE va al final y cubre los nuevos):
  ```bash
  cd ~/repositorios/innova/innova-backend-serverless
  pnpm import:catalog --input=../innova-ai-engine/out/error_catalog.jsonl --dry-run   # validar 2607
  pnpm import:catalog --input=../innova-ai-engine/out/error_catalog.jsonl             # create-if-absent
  docker exec -i innova-postgres-dev psql -U postgres -d innova_dev_db \
    -c "UPDATE error_tags SET status='ACTIVE' WHERE status='DRAFT';"
  pnpm codegen:error-tags
  ```
  Primero staging, luego prod. El dry-run nunca escribe.
- → Archivo: `docs/ai-logs/2026-06-14-error-catalog-deepfill.md`
