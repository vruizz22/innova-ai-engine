# PLAN v8 — Addendum innova-ai-engine

> v8 · 2026-05-18 · Supersede `PLAN_v7_ADDENDUM.md`.
> Master plan: `../../docs/MASTER_PLAN_v8.md`. ADRs: 109-115.
> **Regla #0:** ver `CLAUDE.md §0` — el agente NO ejecuta `uv sync/add`, `serverless deploy`, suites pytest largas.

---

## Contexto: dónde estamos

✅ **v7 completado parcialmente:**

- OCR (Gemini → Claude fallback) funcional.
- LLM classifier con prompt caching + tool_use forzado.
- BKT y IRT calibradores nightly.

🔴 **v7 pendiente:**

- `hourly_alerts.py` (Alert Generator Lambda).
- `ocr_worker.py` no publica a `attempt-reprocess-queue` aún.
- `curriculum_loader.py` solo parsea 3ero-6to (necesita full K-12).

🟡 **v8 nuevo:**

- Scraper de `curriculumnacional.cl` para OA codes oficiales.
- Generador de catálogo de errores con Claude Opus 4 (≥2540 entries).
- Selective domain context en LLM classifier.
- 19 prompts cacheados (uno por dominio).

---

## Sprint A1 (M13 — Curriculum loader full K-12)

### A1.1 Refactor `scripts/curriculum_loader.py`

Antes: solo `3ero..6to.txt`. Ahora: `1ero..4to-medio.txt` (12 archivos).

```python
# Estructura del JSON de salida (por grado):
{
  "grade": "G5",
  "grade_label": "5° básico",
  "source_files": ["5to.txt"],
  "scraped_url": "https://www.curriculumnacional.cl/curriculum/1o-6o-basico/matematica/5-basico",
  "scraped_at": "2026-05-18T12:00:00Z",
  "units": [
    {
      "name": "Números hasta 1.000.000",
      "order": 1,
      "topics": [
        {
          "name": "Valor posicional",
          "subdomain_code": "ARITH_PLACE_VALUE",
          "oa_codes": ["MA05 OA 01"],
          "prerequisites": ["G4.U1.T1"]
        }
      ]
    }
  ]
}
```

Salida: `out/curriculum/curriculum-{g1..g12m}.json` × 12 archivos.

### A1.2 Scraper `scripts/oa_scraper.py` (NUEVO)

- Lee URLs de `links.md` (raíz del repo).
- Para cada URL: GET con User-Agent identificable (`Innova EdTech Curriculum Loader/1.0 contacto@innova.cl`), respeta robots.txt.
- Parsea HTML con BeautifulSoup buscando bloques de OA (`<div class="oa">` o equivalente — inspeccionar HTML real).
- Cache local en S3 `innova-curriculum-cache-prod/curriculumnacional/<grade>.html` con TTL 30 días.
- Output: `out/oa-mapping.json` con `{ oa_code: 'MA05 OA 01', description: '...', grade: 5, suggested_subdomain: 'ARITH_PLACE_VALUE' }`.

### A1.3 PDF loader (NUEVO — adicional)

Los `.txt` macrotipo cubren cuadernos de actividades, NO los textos del estudiante completos. Para subir cobertura:

`scripts/pdf_loader.py`:

- Descarga PDFs oficiales desde `especial.mineduc.cl` (URLs en `links.md`).
- Usa Claude Haiku 4.5 con Vision para extraer estructura (no OCR puro — vision LLM directamente al PDF).
- Cada PDF se procesa en chunks de 10 páginas (limit Claude).
- Salida: JSON con `units[]` y `topics[]`, junto con `examples[]` (ejemplos de ejercicios encontrados en el texto).
- Costo: 12 PDFs × ~$0.20 c/u = $2.40 one-time.

Comando para Victor:

```bash
cd innova-ai-engine
uv run python scripts/oa_scraper.py --all-grades
uv run python scripts/pdf_loader.py --pdf-urls-from links.md --output out/textbook_structure.json
uv run python scripts/curriculum_loader.py --all-grades \
  --txt-input ../*.txt \
  --oa-mapping out/oa-mapping.json \
  --textbook out/textbook_structure.json \
  --output out/curriculum/
```

**DoD:** 12 archivos JSON, cada uno con units, topics, oa_codes. Total ~200 topics K-12.

---

## Sprint A2 (M15 — Generador de catálogo de errores)

### A2.1 `scripts/error_catalog_generator.py` (NUEVO)

Fases:

#### Fase 1: cargar curated (200 errores)

- Lee `docs/error-taxonomy/*.md` del repo raíz.
- Parsea tablas Markdown.
- Filtra por `source=CURATED` (todos los del repo lo son por defecto).
- Output: `out/error_catalog_curated.jsonl`.

#### Fase 2: generar con Claude Opus 4

Por cada dominio (19 total):

1. Carga prompt: `prompts/error_generator/<domain>.txt` (sistema) + few-shots curados del mismo dominio.
2. Pide ≥100 errores nuevos por dominio, JSON-only output con tool_use forzado.
3. Tool schema: `{ errors: [{ code, name, description, subdomain_code, applicable_grades, diagnostic_hint, remediation, severity }] }`.
4. Output: `out/error_catalog_generated_<domain>.jsonl`.

Comando:

```bash
uv run python scripts/error_catalog_generator.py --domain ARITH --target-count 200
# repetir para los 19 dominios
```

#### Fase 3: dedupe con embeddings

`scripts/error_catalog_dedupe.py`:

- Carga todo (curated + generated).
- Embeddings con `text-embedding-3-small` (OpenAI) o `voyage-3-lite` (Anthropic compatible).
- Similarity threshold: cosine > 0.92 → marca como duplicate.
- Output: `out/error_catalog_dedupe_report.csv` con grupos de duplicates para review humano.

#### Fase 4: review humano (manual)

- Victor + 1 profe pedagogo revisan duplicates y casos LLM dudosos.
- Marcan `accepted`, `edited`, `rejected` en CSV.
- Script `scripts/error_catalog_finalize.py` consume el CSV y emite `out/error_catalog.jsonl` final.

**DoD:** `out/error_catalog.jsonl` con ≥2400 entries totales (200 curated + 2200+ generated post-review). Backend lo importa en sprint S7.

---

## Sprint A3 (M11 v7 finalizar — Alert Generator + OCR loop)

### A3.1 `src/pipeline/hourly_alerts.py`

Mantiene plan de v7 con un cambio:

- Payload incluye `domain_id` y `subdomain_code` para que el dashboard filtre.

### A3.2 Cierre OCR loop

`src/pipeline/ocr_worker.py`:

- Post-extracción, publicar a SQS `attempt-reprocess-queue` (no actualizar Postgres directo).
- Backend consume y re-dispatcha al Rule Engine.

**DoD:** misma de v7 (alert <1h post-attempt, OCR re-clasificado <2 min).

---

## Sprint A4 (M17 — LLM classifier con selective domain context)

### A4.1 Reorganizar `src/llm_classifier/prompts.py`

Antes: un solo `SYSTEM_PROMPT` con toda la taxonomía.

Ahora: `prompts/by_domain/<code>.py` con un prompt por dominio.

```python
# prompts/by_domain/arith.py
ARITH_SYSTEM_PROMPT = """
You are a math error classifier specialized in Arithmetic with Natural Numbers (G1-G6 Chile).

Errors you can detect:
{{ ARITH_ERROR_CATALOG }}  # injected at runtime from DB query

Output schema (use tool_use 'classify_errors'):
{ classifications: [{ attempt_id, error_code, confidence, reasoning }] }
"""
```

### A4.2 `src/llm_classifier/client.py`

Nuevo método `classify_batch_for_domain(attempts, domain_code)`:

- Carga prompt específico del dominio (`prompts/by_domain/<domain>.py`).
- Inyecta catálogo de errores del dominio desde DB (cached 1h con `functools.lru_cache`).
- Llama Claude Haiku 4.5 con `cache_control: ephemeral` en system prompt.
- Cache key = `(model_version, domain_code, catalog_hash)`.

### A4.3 `src/pipeline/llm_consumer.py`

- SQS batch puede tener attempts de domains distintos.
- Worker agrupa por `domain_id` (viene en message body desde backend, ver backend addendum S9.1).
- Llama `classify_batch_for_domain` una vez por grupo.
- Aggrega resultados, escribe a Postgres en una transacción.

### A4.4 Manejo de errores transversales

- Si confidence < 0.6 en todos los errores del dominio: el LLM puede retornar `error_code: TRANSVERSAL_LIKELY` con razonamiento.
- Worker re-encola el attempt con `domain_code=TRANSV` para segundo pase.
- Si el segundo pase tampoco clasifica con confidence ≥ 0.7: marca `UNCLASSIFIED` final.

**DoD:** cache hit rate >85% en smoke test con 100 attempts batch. Costo proyectado <$0.10/1K attempts UNCLASSIFIED.

---

## Sprint A5 (M19 — Load test)

`scripts/load_test_synthetic.py` (NUEVO):

- Genera 1.000 alumnos sintéticos cada uno con 200 attempts en topics aleatorios.
- 70% attempts canónicos correctos.
- 20% attempts con errores conocidos (sampleados del catálogo).
- 10% attempts UNCLASSIFIED reales (rare cases).
- Posts via API a staging.
- Mide:
  - p95 attempt submission latency.
  - p95 LLM async classification latency.
  - SQS queue depth máxima.
  - Costo total Anthropic + Gemini.

**DoD:** p95 attempts <300ms, p95 LLM async <60s. Costo total <$5 USD.

---

## Subdirectorios nuevos en este repo

```
innova-ai-engine/
├── prompts/
│   └── by_domain/
│       ├── arith.py
│       ├── int.py
│       ├── fract.py
│       ├── dec.py
│       ├── ratio.py
│       ├── algebra_linear.py
│       ├── algebra_quad.py
│       ├── pow.py
│       ├── func.py
│       ├── geom.py
│       ├── geom3d.py
│       ├── trig.py
│       ├── stat.py
│       ├── data.py
│       ├── log.py
│       ├── seq.py
│       ├── coord.py
│       └── transv.py
├── scripts/
│   ├── curriculum_loader.py       (refactor v8)
│   ├── oa_scraper.py              (NUEVO)
│   ├── pdf_loader.py              (NUEVO — Claude Vision sobre PDFs MINEDUC)
│   ├── error_catalog_generator.py (NUEVO)
│   ├── error_catalog_dedupe.py    (NUEVO)
│   ├── error_catalog_finalize.py  (NUEVO)
│   └── load_test_synthetic.py     (NUEVO)
└── out/                            (gitignored, outputs locales)
    ├── curriculum/
    ├── oa-mapping.json
    └── error_catalog*.jsonl
```

---

## Costos proyectados v8 (one-time setup)

| Item | Costo |
|---|---|
| `pdf_loader.py` con Claude Haiku Vision sobre 12 PDFs | $2.40 |
| `error_catalog_generator.py` con Claude Opus 4 (~$15/M output × ~150K tokens × 19 dominios) | ~$45 |
| Embeddings dedupe (~3K errores × $0.00002/embedding) | $0.06 |
| **Total setup v8** | **~$50 one-time** |

Después: catálogo vive en DB, no se regenera.

---

## Backlog técnico v8

- [ ] Async Gemini (`generate_content_async`) — pendiente de v7.
- [ ] Property-based tests BKT con Hypothesis (pendiente v7).
- [ ] Cobertura tests ≥75% en `src/` (gate de CI).
- [ ] Métricas custom CloudWatch: `catalog.draft_count`, `catalog.deprecated_count`, `llm.cache_hit_rate_by_domain`.
