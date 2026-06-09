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

> **Pase 1 (breadth-complete): 253 entries validadas** — 17/17 dominios, grados 1–12.
> Validadas contra el schema Zod del importador (0 inválidas, 0 duplicados).
> Pases siguientes = profundidad (más variantes por subdominio) hasta acercarse al objetivo ≥2540.

| Archivo | Dominio | Grados | Entries | Estado |
|---|---|---|---|---|
| `01-arith.jsonl` | ARITH | 1–6 | 46 | ✅ pase 1 |
| `02-int.jsonl` | INT | 7–8 | 16 | ✅ pase 1 |
| `03-fract.jsonl` | FRACT | 4–8 | 18 | ✅ pase 1 |
| `04-dec.jsonl` | DEC | 5–8 | 15 | ✅ pase 1 |
| `05-ratio.jsonl` | RATIO | 6–10 | 13 | ✅ pase 1 |
| `06-algebra.jsonl` | ALGEBRA | 7–12 | 26 | ✅ pase 1 |
| `07-pow.jsonl` | POW | 8–12 | 14 | ✅ pase 1 |
| `08-func.jsonl` | FUNC | 9–12 | 17 | ✅ pase 1 |
| `09-geom.jsonl` | GEOM | 3–10 | 18 | ✅ pase 1 |
| `10-geom3d.jsonl` | GEOM3D | 6–11 | 9 | ✅ pase 1 |
| `11-trig.jsonl` | TRIG | 9–12 | 10 | ✅ pase 1 |
| `12-stat.jsonl` | STAT | 5–12 | 11 | ✅ pase 1 |
| `13-data.jsonl` | DATA | 3–8 | 8 | ✅ pase 1 |
| `14-log.jsonl` | LOG | 11–12 | 8 | ✅ pase 1 |
| `15-seq.jsonl` | SEQ | 6–10 | 7 | ✅ pase 1 |
| `16-coord.jsonl` | COORD | 5–12 | 8 | ✅ pase 1 |
| `17-transv.jsonl` | TRANSV | todos | 9 | ✅ pase 1 |

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
pnpm tsx scripts/import-error-catalog.ts --input=../innova-ai-engine/out/catalog/01-arith.jsonl --dry-run

# 3. Combinar todos los dominios e importar de verdad (idempotente, upsert por code)
cat ../innova-ai-engine/out/catalog/*.jsonl > ../innova-ai-engine/out/error_catalog.jsonl
pnpm tsx scripts/import-error-catalog.ts --input=../innova-ai-engine/out/error_catalog.jsonl

# 4. (Tras revisión pedagógica) pasar DRAFT → ACTIVE y regenerar el enum TS
#    psql "$DATABASE_URL" -c "UPDATE error_tags SET status='ACTIVE' WHERE status='DRAFT';"
pnpm tsx scripts/codegen-error-tags.ts
```

> Primero contra **staging**, luego prod. El dry-run nunca escribe.
