# Bug Fix: la revisión automática del agente avisa de lo que no hay

- **Slug**: la-revision-ve-lo-que-no-hay
- **Fixed**: 2026-11-26
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

La revisión deja de marcar las frases del texto real de Jemma: «El equipo no confirma las
citas» ya no prohíbe la agenda, un precio se compara por su importe (como lo escribe la ficha
y como lo escribe una persona) y un rango solo es un horario si parece una hora, en una frase
del horario, y se compara contra todas las horas de la ficha. En la consola, la «Revisión
automática» de la tarjeta de pruebas ya no repite una a una las promesas que enseña «No
tenemos herramienta para».

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/services/agent_spec/compiler.py` | modified | `_TEAM_SUBJECT` en `_refused`; `_team_checks`; `_PRICE`, `_FICHA_PRICE` y `_value`; `_TIME_RANGE`, `_NOT_A_TIME_AFTER`, `_HOURS_SENTENCE`, `_ficha_hours` y `_hours_said` |
| `apps/api/tests/unit/test_agent_spec_compiler.py` | modified / added tests | El fixture escribe el precio con `format_amount`; cinco pruebas nuevas |
| `apps/console/src/components/builder/tests-box.tsx` | modified | Las `promises_without_tool`, en una línea con «Ver cuáles» (`#agente-faltan`) |
| `apps/console/src/components/builder/__tests__/tests-box.test.tsx` | added test | Con axe |
| `apps/console/src/i18n/lanes/builder-quality.ts` | modified | `builder.review.promises.above.{one,other}`, `builder.review.promises.see` |

## Diff Highlights

- Negación del equipo: `_refused` no cuenta una negación cuyo sujeto, justo antes, es el
  equipo (`\b{_TEAM}\b … (no|nunca|jamás)\s+$`); `_team_checks` descarta una coincidencia de
  `_TEAM_CHECKS` que lleve o tenga delante una negación.
- Precios: `_NUMBER = \d+(?:[.,]\d{3})*(?:[.,]\d{1,2})?` con borde a la izquierda; el
  símbolo delante (`$`, `US$`, `€`) o la moneda detrás (símbolos, nombres y códigos); en la
  ficha, cualquier código ISO en mayúsculas. Se compara `Decimal`: «30», «30,00» y «30.00»
  son lo mismo.
- Horario: la frase se corta sin partir «10.30»; el rango necesita «de/desde», `:mm`, `h`,
  `hs`, `am` o `pm`, números ≤ 24 y minutos ≤ 59, y no lleva detrás «personas», «horas»,
  «días»… ni «de antelación». Las horas conocidas son las del negocio, el «Horario propio»
  de cada sede (solo esa parte de la línea) y las de las fechas especiales, con la hora de 12.

## Tests Added or Updated

- `test_agent_spec_compiler.py::test_the_team_not_confirming_does_not_forbid_the_agenda` —
  la frase de Jemma, cada rama por separado, y lo que sigue prohibiendo.
- `::test_a_price_said_another_way_is_the_same_price` — «30 USD», «$30», «US$ 30», «30
  dólares», «30,00 USD» y «30.00 USD» contra «30,00 USD»; «1500 USD» entero; un precio
  distinto sigue avisando.
- `::test_the_currencies_the_ficha_writes_are_read` — EUR, CLP, MXN con `format_amount`.
- `::test_a_range_that_is_not_a_time_is_not_an_hour` — personas, horas de antelación, días;
  «Abrimos de 9 a 21» sigue avisando; la hora de 12.
- `::test_the_hours_of_a_location_or_a_special_date_are_hours_of_the_ficha` — y los dígitos
  de la dirección o del teléfono no cuentan.
- `::test_the_same_hours_and_prices_are_not_a_contradiction` — ya existía; con el fixture
  nuevo, en rojo antes del arreglo.
- `tests-box.test.tsx` — «la revisión de la tarjeta no repite lo que falta».

## Local Verification

- `pytest tests/unit/test_agent_spec_compiler.py` antes → 6 failed, 16 passed; después → 22 passed.
- `pytest` de `test_agent_review.py`, `test_agent_spec_compiler.py`, `test_only_what_we_have.py`,
  `test_057_agenda_routes.py`, `test_057_agenda_text_job.py`, `test_review_and_catalog.py`,
  `test_migration_0229_agenda_from_agent.py`, `tests/isolation/test_057_agenda_from_agent.py`
  y `test_agent_draft_job.py` → 119 passed.
- `vitest run` de `tests-box`, `agent-builder`, `review-panel` y `missing-capabilities` antes →
  1 failed; después → 96 passed.
- `ruff check`, `ruff format`, `mypy --strict` de `compiler.py` → limpio.
- Las expresiones nuevas con textos de 2.000 a 5.000 caracteres: ≤ 2 ms.

## Deviations from Assessment

- No se dedujo nada de ReviewPanel ni de la hoja de PublishBar: ReviewPanel es la revisión
  entera (en «Más ajustes») y la hoja enseña lo que impide guardar en el momento de guardar.
  Que «No tenemos herramienta para» y la revisión salgan juntos en la misma columna se decide
  en `agent-builder.tsx` (de la 082): queda anotado en la carpeta común.

## Follow-ups

- Comparar también la moneda (no solo el importe) si Luis lo quiere: menos falsos negativos,
  más ruido con «$».
