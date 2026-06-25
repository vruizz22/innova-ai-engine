# Error Catalog — JSONL source para `import-error-catalog.ts`

> Generado por agente Claude Code (Opus 4.8) usando la suscripción Claude Code (costo $0,
> sin gastar `ANTHROPIC_API_KEY`). Implementa Fase 2 (LLM-augmented) de
> `docs/error-taxonomy-generation-plan.md`, con calidad curada.

## Qué es esto

Un archivo `.jsonl` por dominio matemático. Cada línea es una entry validada contra el
schema Zod de `innova-backend-serverless/scripts/import-error-catalog.ts`:

```
code, name, description, domain_code, subdomain_code, severity,
source, status, applicable_grades[], diagnostic_hint?, remediation?, references[]
```

- `applicable_grades`: enteros 1–12 (1=1°básico … 8=8°básico, 9=1°medio … 12=4°medio).
- `code`: `<DOMAIN>_<SUBDOMAIN>_<NAME>_<GRADE_HINT>` (SCREAMING_SNAKE_CASE, estable).
- `status`: **DRAFT** en todas (gate de revisión pedagógica antes de pasar a ACTIVE).
- `source`: `CURATED` para errores documentados en literatura, `LLM_GENERATED` para el resto.

> Los tags especiales (`CORRECT`, `UNCLASSIFIED`) y los curados base ya viven en
> `prisma/seed.ts` con `status=ACTIVE` — NO se repiten aquí (el importador los saltaría como
> duplicados de todas formas, ya que upsert es por `code`).

## Cobertura (K-12 matemática, MINEDUC FG)

> **Estado actual: 2607 entries validadas** — 17/17 dominios, grados 1–12. **Objetivo ≥2540 superado.**
> Validadas con `out/catalog/validate_catalog.py` (0 inválidas, 0 duplicados, 2607 codes únicos).
> Deep-fill completo: cada dominio se llevó al/por sobre su target de `docs/error-taxonomy/README.md §3`,
> mediante diff de los IDs estables de los docs `docs/error-taxonomy/NN-*.md` contra el catálogo +
> revisión del deployed por subdominio (se añaden solo conceptos genuinamente nuevos para evitar
> duplicado semántico; el plan tiene un paso posterior de dedup por embeddings).

| Archivo | Dominio | Grados | Entries | Target |
|---|---|---|---|---|
| `01-arith.jsonl` | ARITH | 1–6 | 286 | 280 |
| `02-int.jsonl` | INT | 7–8 | 139 | 120 |
| `03-fract.jsonl` | FRACT | 4–8 | 196 | 180 |
| `04-dec.jsonl` | DEC | 5–8 | 194 | 140 |
| `05-ratio.jsonl` | RATIO | 6–10 | 112 | 110 |
| `06-algebra.jsonl` | ALGEBRA | 7–12 | 380 | 380 |
| `07-pow.jsonl` | POW | 8–12 | 160 | 160 |
| `08-func.jsonl` | FUNC | 9–12 | 180 | 180 |
| `09-geom.jsonl` | GEOM | 3–10 | 170 | 170 |
| `10-geom3d.jsonl` | GEOM3D | 6–11 | 110 | 110 |
| `11-trig.jsonl` | TRIG | 9–12 | 130 | 130 |
| `12-stat.jsonl` | STAT | 5–12 | 130 | 130 |
| `13-data.jsonl` | DATA | 3–8 | 70 | 70 |
| `14-log.jsonl` | LOG | 11–12 | 80 | 80 |
| `15-seq.jsonl` | SEQ | 6–10 | 90 | 90 |
| `16-coord.jsonl` | COORD | 5–12 | 100 | 100 |
| `17-transv.jsonl` | TRANSV | todos | 80 | 80 |
| **TOTAL** | | | **2607** | **2540** |

Validar localmente en cualquier momento:
```bash
python3 - <<'PY'
import json,re,glob
rx=re.compile(r'^[A-Z][A-Z0-9]*_[A-Z][A-Z0-9]*_[A-Z][A-Z0-9_]*$')
n=bad=0
for f in glob.glob('innova-ai-engine/out/catalog/*.jsonl'):
    for ln in open(f,encoding='utf-8'):
        ln=ln.strip()
        if not ln: continue
        n+=1
        o=json.loads(ln)
        if not rx.match(o['code']): bad+=1; print('BAD',o['code'])
print(n,'entries,',bad,'invalidas')
PY
```

## Runbook (lo corre Victor — regla install-by-user)

```bash
# 0. Prerequisito: regenerar cliente Prisma + crear/aplicar migración v8 (resuelve los 3 errores TS)
cd innova-backend-serverless
pnpm prisma migrate dev --name plan_v8_error_taxonomy   # genera migración + regenera cliente
# (en CI/prod: pnpm prisma migrate deploy)

# 1. Sembrar dominios/subdominios + tags base (el importador exige Domains presentes)
pnpm prisma db seed

# 2. Validar el catálogo SIN escribir (dry-run) — un dominio o el combinado
#    (este repo usa ts-node, NO tsx; el script vive como pnpm script "import:catalog")
pnpm import:catalog --input=../innova-ai-engine/out/catalog/01-arith.jsonl --dry-run

# 3. Combinar todos los dominios e importar de verdad (idempotente, upsert por code)
cat ../innova-ai-engine/out/catalog/*.jsonl > ../innova-ai-engine/out/error_catalog.jsonl
pnpm import:catalog --input=../innova-ai-engine/out/error_catalog.jsonl

# 4. (Tras revisión pedagógica) pasar DRAFT → ACTIVE y regenerar el enum TS
#    psql "$DATABASE_URL" -c "UPDATE error_tags SET status='ACTIVE' WHERE status='DRAFT';"
pnpm codegen:error-tags
```

> Primero contra **staging**, luego prod. El dry-run nunca escribe.
