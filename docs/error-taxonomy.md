# Error Taxonomy — Procedural Math Errors (3°–6° básico chileno)

> Versión MVP 1.0 · 2026-04-29
> Curaduría inicial: equipo Innova (Victor lead). Validación pedagógica pendiente con profe real en M3.
> Fuente teórica: Brown & VanLehn (1980) "Repair Theory" + Resnick & Ford (1981) + Mack (1990) + curriculum MINEDUC OA 3°-6°.

## Filosofía de la taxonomía

- **Identificadores estables**: SCREAMING_SNAKE_CASE, no se renombran nunca (forman parte del enum-like consumido por LLM tool_use).
- **Granularidad práctica**: cada error_type debe ser detectable por una regla determinista clara O describible al LLM en <2 líneas.
- **No exhaustivo**: si un attempt no matchea, etiqueta `UNCLASSIFIED` y se enruta al LLM async (Capa 4).
- **Especiales**: `CORRECT` y `UNCLASSIFIED` siempre disponibles.
- **Versionado**: nuevas error_types se agregan AL FINAL (no se reordenan), bumping la versión del taxonomía.

---

## Topic 1: `subtraction_borrow` (Resta con reserva)

**Grado:** 3°-4° básico. **Curriculum:** OA 6 (3°), OA 5 (4°). **MVP — Entrega 2 (3 May).**

### MVP error_types (8)

| ID | Nombre | Descripción | Patrón regla | Ejemplo |
|----|--------|-------------|--------------|---------|
| 1 | `BORROW_OMITTED_TENS` | El alumno restó la columna unidades sin pedir prestado a las decenas. Resultado: dígitos abs-value o swap. | `student_units_digit == abs(a_units - b_units)` cuando `b_units > a_units` | 53 − 26: escribe "33" (en vez de 27, hizo 6−3=3 en unidades) |
| 2 | `BORROW_OMITTED_HUNDREDS` | Igual que (1) pero en columna centenas. | Análogo, columna 100s | 423 − 156: omite borrow de centenas |
| 3 | `SUBTRAHEND_MINUEND_SWAPPED` | El alumno restó al revés (sustrayendo el mayor del menor). | `student_answer == b - a` (resultado negativo o invertido) | 53 − 26 → "27" pero student wrote 26 − 53 first y dio el abs |
| 4 | `BORROW_FROM_ZERO_INCORRECT` | Alumno tiene que pedir prestado a una columna con 0; lo hace mal (ej. transforma 0→9 sin propagar). | Detección por análisis del paso intermedio en `rawSteps` | 100 − 27: escribe "83" (debería ser 73) |
| 5 | `STOP_BORROW_PROPAGATION` | Borrow se propaga por múltiples ceros y el alumno detiene la propagación a media columna. | Análisis de `rawSteps` en problemas con cadena de ceros | 1000 − 1: escribe "999" en vez de seguir bajando dígitos |
| 6 | `DIGIT_TRANSPOSITION` | Resultado correcto pero con dos dígitos transpuestos. | Multiset de dígitos = expected pero orden distinto | 53 − 26 → escribe "72" (transposición de "27") |
| 7 | `COLUMN_MISALIGNMENT` | Alumno alineó verticalmente mal (centenas con decenas, etc.) | Detección por bounding-box en OCR o por `rawSteps[].column` mismatch | 53 + 6 escrito como 53/+_6 mal alineado |
| 8 | `ARITHMETIC_FACT_ERROR` | Off-by-one o ±1 en hechos básicos (7-3=5 en vez de 4). Fallback regla cuando ninguna otra matchea pero `\|student_answer - expected\| ≤ 2`. | Magnitude diff small | 53 − 26 → "26" (cerca pero no exacto, no estructural) |

### Notas de implementación

- Las reglas 1, 3, 6 son **deterministas y simples** → cobertura ~50%.
- Las reglas 4, 5, 7 requieren **análisis de `rawSteps`** → solo aplicables cuando el alumno usa `math-input` digital. Si el input viene de OCR sin pasos intermedios visibles, se enrutan a UNCLASSIFIED.
- La regla 8 es un **catch-all conservador**: solo dispara si no hay match estructural.

---

## Topic 2: `addition_carry` (Suma con llevadas)

**Grado:** 3° básico. **Curriculum:** OA 5. **Target: Entrega 3 (7 Jun).**

| ID | Nombre | Descripción | Ejemplo |
|----|--------|-------------|---------|
| 9 | `CARRY_OMITTED` | No agregó la llevada a la columna siguiente. | 38 + 27: escribe "55" (omitió +1 en decenas) |
| 10 | `CARRY_ADDED_TO_WRONG_COLUMN` | Agregó la llevada a columna equivocada. | 38 + 27: escribe "65" (sumó la llevada a unidades) |
| 11 | `DIGIT_TRANSPOSITION` (reusa ID 6) | — | — |
| 12 | `COLUMN_MISALIGNMENT` (reusa ID 7) | — | — |
| 13 | `ARITHMETIC_FACT_ERROR` (reusa ID 8) | — | — |

---

## Topic 3: `fractions_addsub_same_denom` (Suma/resta de fracciones, mismo denominador)

**Grado:** 5° básico. **Curriculum:** OA 9. **Target: Entrega 3 (7 Jun).**

| ID | Nombre | Descripción | Ejemplo |
|----|--------|-------------|---------|
| 14 | `SUM_NUMERATORS_AND_DENOMINATORS` | Sumó/restó numeradores Y denominadores. | 2/5 + 1/5 = "3/10" (en vez de 3/5) |
| 15 | `IMPROPER_FRACTION_NOT_REDUCED` | Resultado correcto pero no reducido a forma simple. | 2/4 (en vez de 1/2) |
| 16 | `INVERTED_FRACTION` | Inversión accidental numerador/denominador. | 3/5 → escribe 5/3 |
| 17 | `WHOLE_NUMBER_LOST` | En sumas con números mixtos pierde la parte entera. | 1 1/4 + 1/4 → "2/4" (perdió el 1) |
| 18 | `ARITHMETIC_FACT_ERROR` (reusa ID 8) | — | — |

---

## Topics futuros (Entrega 4, 19 Jun)

### `mult_single_digit` (Multiplicación 1-dígito × 1-dígito o 2-dígito)

| ID | Nombre | Ejemplo |
|----|--------|---------|
| 19 | `TABLE_RECALL_ERROR` | 7 × 8 = 54 (en vez de 56) |
| 20 | `CARRY_OMITTED_MULT` | 27 × 3: escribe "61" |
| 21 | `ZERO_TIMES_X_NONZERO` | 0 × 5 = 5 |

### `division_long` (División larga)

| ID | Nombre | Ejemplo |
|----|--------|---------|
| 22 | `DIVISOR_DIVIDEND_SWAPPED` | 124 ÷ 4 escrito como 4 ÷ 124 |
| 23 | `REMAINDER_GREATER_THAN_DIVISOR` | 17 ÷ 5 = 2 r 7 |
| 24 | `BRING_DOWN_OMITTED` | 124 ÷ 4: omite bajar el dígito siguiente |

### `fractions_addsub_diff_denom` (denominadores distintos)

| ID | Nombre | Ejemplo |
|----|--------|---------|
| 25 | `COMMON_DENOMINATOR_MISSED` | 1/2 + 1/3: suma directa sin denominador común |
| 26 | `WRONG_LCM` | 1/4 + 1/6 con LCM=10 (debería 12) |

---

## Casos especiales (siempre presentes)

| ID | Nombre | Cuándo |
|----|--------|---------|
| 0 | `CORRECT` | `final_answer == canonical_solution` (igualdad estricta tras normalización). |
| -1 | `UNCLASSIFIED` | Ninguna regla matchea. Se enruta a SQS LLM queue para clasificación async. |

---

## Schema TypeScript canónico

```typescript
// packages/types/src/errors.ts (innova-clients) y src/modules/attempts/error-types.ts (backend)
export const ErrorType = {
  // SUBTRACTION_BORROW
  BORROW_OMITTED_TENS:           'BORROW_OMITTED_TENS',
  BORROW_OMITTED_HUNDREDS:       'BORROW_OMITTED_HUNDREDS',
  SUBTRAHEND_MINUEND_SWAPPED:    'SUBTRAHEND_MINUEND_SWAPPED',
  BORROW_FROM_ZERO_INCORRECT:    'BORROW_FROM_ZERO_INCORRECT',
  STOP_BORROW_PROPAGATION:       'STOP_BORROW_PROPAGATION',
  DIGIT_TRANSPOSITION:           'DIGIT_TRANSPOSITION',
  COLUMN_MISALIGNMENT:           'COLUMN_MISALIGNMENT',
  ARITHMETIC_FACT_ERROR:         'ARITHMETIC_FACT_ERROR',

  // ADDITION_CARRY (Entrega 3)
  CARRY_OMITTED:                 'CARRY_OMITTED',
  CARRY_ADDED_TO_WRONG_COLUMN:   'CARRY_ADDED_TO_WRONG_COLUMN',

  // FRACTIONS_ADDSUB_SAME_DENOM (Entrega 3)
  SUM_NUMERATORS_AND_DENOMINATORS:'SUM_NUMERATORS_AND_DENOMINATORS',
  IMPROPER_FRACTION_NOT_REDUCED: 'IMPROPER_FRACTION_NOT_REDUCED',
  INVERTED_FRACTION:             'INVERTED_FRACTION',
  WHOLE_NUMBER_LOST:             'WHOLE_NUMBER_LOST',

  // MULT_SINGLE_DIGIT (Entrega 4)
  TABLE_RECALL_ERROR:            'TABLE_RECALL_ERROR',
  CARRY_OMITTED_MULT:            'CARRY_OMITTED_MULT',
  ZERO_TIMES_X_NONZERO:          'ZERO_TIMES_X_NONZERO',

  // DIVISION_LONG (Entrega 4)
  DIVISOR_DIVIDEND_SWAPPED:      'DIVISOR_DIVIDEND_SWAPPED',
  REMAINDER_GREATER_THAN_DIVISOR:'REMAINDER_GREATER_THAN_DIVISOR',
  BRING_DOWN_OMITTED:            'BRING_DOWN_OMITTED',

  // FRACTIONS_ADDSUB_DIFF_DENOM (Entrega 4)
  COMMON_DENOMINATOR_MISSED:     'COMMON_DENOMINATOR_MISSED',
  WRONG_LCM:                     'WRONG_LCM',

  // Especiales
  CORRECT:                       'CORRECT',
  UNCLASSIFIED:                  'UNCLASSIFIED',
} as const;

export type ErrorTypeValue = typeof ErrorType[keyof typeof ErrorType];
```

---

## Próximos pasos

1. Validar este catálogo con un profe real de matemáticas básica antes de M3 (target: 1ª semana de mayo).
2. Generar fixtures de attempts canónicos por error_type para tests del rule engine (3 ejemplos por type → 24 fixtures MVP).
3. Generar few-shots curados para el LLM prompt (5 ejemplos por type → 40 few-shots).
4. Tradución del catálogo a español natural para el componente `error-renderer` (texto explicativo amistoso al alumno).
