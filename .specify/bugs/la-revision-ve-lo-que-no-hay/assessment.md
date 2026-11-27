# Bug Assessment: la revisión automática del agente avisa de lo que no hay

- **Slug**: la-revision-ve-lo-que-no-hay
- **Created**: 2026-11-26
- **Source**: pasted text (sesión principal de la beta de Jemma, 2026-11-26; nota de KB `research/2026-11-26-beta-jemma-p0-p1.md`, sección 081, B2). Sin URL.
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

> `forbids_agenda("El equipo no confirma las citas.")` devuelve `True`, porque no entiende
> la negación. En `contradicts_business`: `_amount` convierte «30 USD» en `30` y «30,00 USD»
> de la ficha en `3000`, así que no casan; «$30» no lo reconoce; «EUR» no está en `_PRICE`;
> cualquier «N a M» cerca de una palabra de horario se marca, aunque hable de personas o de
> horas de plazo; solo compara contra el horario del negocio: ignora el de las sedes y las
> fechas especiales. El mismo hallazgo aparece en cuatro sitios: MissingCapabilities,
> TestsBox, ReviewPanel y PublishBar. Las pruebas unitarias ocultan el problema: el fixture
> usa «15,00 €».

## Symptom

Con el texto real de Jemma, la revisión del borrador avisa de que el agente se prohíbe la
agenda y de que contradice la ficha cuando no es así, y repite cada aviso en varios sitios
de la misma pantalla. Quien construye el agente deja de fiarse de la revisión. Lo esperado:
solo avisa de lo que de verdad contradice la ficha o prohíbe la agenda, una vez por sitio
donde se decide algo.

## Reproduction

Comprobado el 2026-11-26 en el worktree, sobre `main` `44a43298`:

```text
forbids_agenda("El equipo no confirma las citas.")      → True
  _refuses_slots(...)                                    → True   (lee «no confirma las citas» como orden al agente)
  _TEAM_CHECKS.search(...)                               → match  (el relleno de 0–5 palabras se traga el «no»)
_amount("30") → "30";  _amount("30,00") → "3000"
_PRICE en «cuesta $30»   → []          (el símbolo delante no se lee)
_PRICE en «30 EUR»       → []          (format_amount escribe el código ISO; solo hay €, euros, $, usd, clp, pesos, mxn)
_PRICE en «1500 USD»     → ["500 USD"] (sin borde a la izquierda)
_TIME_RANGE + _HOURS_WORDS en «Atendemos grupos de 2 a 4 personas» → «de 2 a 4» marcado como horario
```

La ficha escribe los precios con `services_catalog.format_amount`: «30,00 USD», «15.000 CLP»,
«15,00 EUR». El fixture de las pruebas unitarias escribe a mano «15,00 €», que nunca sale de
la ficha.

## Suspected Code Paths

- `apps/api/src/nexus_api/services/agent_spec/compiler.py:497` (`_refused`) — la negación
  delante del verbo cuenta aunque el sujeto sea el equipo («el equipo no confirma»).
- `compiler.py:442` (`_TEAM_CHECKS`) — el relleno `(\s+(?!(y|e|o|u|cuando|si|mientras)\b)\w+){0,5}?`
  admite «no», «nunca», «jamás».
- `compiler.py:328` (`_TIME_RANGE`) y `:332` (`_HOURS_WORDS`) — la palabra de horario se busca
  en todo el texto y el rango puede estar en cualquier sitio; nada mira qué viene detrás del
  rango (personas, horas, días…).
- `compiler.py:334` (`_PRICE`) — moneda solo detrás, lista cerrada, sin borde izquierdo.
- `compiler.py:618` (`_numbers`) y `:622` (`_amount`) — solo el horario del negocio; el importe
  quita los separadores, así que «30» y «30,00» no casan.
- `compiler.py:649-676` (`incoherences`, rama `facts`) — compara contra `facts.hours`, no
  contra «Horario propio» de las sedes (`facts.locations`) ni contra `facts.special_dates`.
- `apps/api/tests/unit/test_agent_spec_compiler.py:38` — el fixture.
- Consola: `promises_without_tool` sale de la misma `incoherences` como
  `missing_capabilities` (`services/agent_spec/missing.py:91`) y como hallazgo de la
  revisión. En la pestaña «Construir» se pinta a la vez en MissingCapabilities (columna
  principal) y en la «Revisión automática» de TestsBox (columna derecha,
  `tests-box.tsx:392-478`); también en ReviewPanel (dentro de «Más ajustes») y, al guardar
  con bloqueo, en la hoja de PublishBar (`publish-bar.tsx:496-536`). Los cuatro se montan
  desde `agent-builder.tsx`, que es de la sesión 082.

## Root Cause Hypothesis

Confianza alta: cada caso se reproduce con la función. Las expresiones se escribieron
contra textos de prueba («15,00 €», «Abrimos de 9 a 21», «No ofrezcas huecos») y no contra
la forma en que la ficha escribe sus datos ni contra frases en tercera persona del equipo.

## Proposed Remediation

**Preferred**:

1. **La negación del equipo**: `_refused` no cuenta una negación cuyo sujeto, en la misma
   cláusula y justo antes, es el equipo («el equipo no confirma»): es lo que hace el equipo,
   no una orden al agente. `_TEAM_CHECKS` no admite negaciones en su relleno. Siguen en
   `True`: «El equipo confirma las citas», «No confirmes las citas», «Las citas las
   confirma el equipo».
2. **Precios**: leer el importe con la gramática de la propia expresión (grupos de tres
   dígitos son miles; uno o dos dígitos al final, decimales) y compararlo como número
   (`Decimal`), no como cadena de dígitos. Borde izquierdo (`(?<![\d.,])`). Moneda delante
   (`$`, `US$`, `€`) o detrás (símbolos, nombres y cualquier código ISO de tres letras en
   mayúsculas, que es lo que escribe `format_amount`). Se compara el importe, no la moneda:
   «30 USD» y «$30» casan con «30,00 USD».
3. **Horario**: la palabra de horario y el rango en la misma frase; el rango debe parecer una
   hora (con `:mm`, `h`, `hs`, `am`/`pm`, o con «de/desde … a/hasta …»), con números ≤ 24, y
   sin un sustantivo que no sea de hora detrás («personas», «horas», «días», «minutos»,
   «semanas», «años», «clientes», «citas»…). Se compara contra todas las horas de la ficha:
   el horario del negocio, el «Horario propio» de cada sede (solo esa parte de la línea, que
   también lleva dirección y teléfono) y las fechas especiales. Con hora de 12: «de 9 a 7»
   casa con «19:00».
4. **El fixture**: los precios de las pruebas se escriben con `format_amount`, y se añaden
   las frases reales de Jemma.
5. **Consola**: la «Revisión automática» de TestsBox deja de repetir uno a uno los
   `promises_without_tool`, que MissingCapabilities ya enseña encima con su arreglo: los
   resume en una línea con enlace a «Lo que falta». ReviewPanel (la revisión entera, en «Más
   ajustes») y la hoja de bloqueo de PublishBar (lo que impide guardar, en el momento de
   guardar) se quedan: cada uno decide algo distinto. Lo que solo se arregla en
   `agent-builder.tsx` se deja anotado para la 082.

**Alternatives**:
- Comparar también la moneda: más contradicciones verdaderas («30 €» con ficha en USD), pero
  más ruido con negocios que dicen «$» por dólares o pesos; descartada por ahora.

**Files likely to change**:
- `apps/api/src/nexus_api/services/agent_spec/compiler.py`
- `apps/api/tests/unit/test_agent_spec_compiler.py`
- `apps/console/src/components/builder/tests-box.tsx` y su prueba

**Tests to add or update**:
- Las frases de Jemma: «El equipo no confirma las citas.» no prohíbe la agenda; cada rama
  por separado (`_refused`, `_TEAM_CHECKS`).
- Lo que sigue prohibiendo: «No confirmes las citas», «El equipo confirma las citas», «Las
  citas las confirma el equipo».
- Precios con `format_amount` («30,00 USD», «15.000 CLP», «15,00 EUR») contra «30 USD»,
  «$30», «US$ 30», «30 dólares», «15000 pesos», «15 €»; «1500 USD» se lee entero; un precio
  distinto sigue avisando.
- Horario: «grupos de 2 a 4 personas», «cancela con 24 a 48 horas», «de 2 a 3 días» no
  avisan; «Abrimos de 9 a 21» con ficha de 10 a 20 sigue avisando; el horario de una sede o
  de una fecha especial no avisa.
- Consola: en TestsBox, un `promises_without_tool` no se lista uno a uno.
- Las pruebas de `agenda_text.py` y `agent_draft.py`, que llaman a `forbids_agenda`.

## Risks & Considerations

- Menos avisos también puede ser algún aviso verdadero menos: por eso cada regla nueva lleva
  su caso que sigue avisando.
- `forbids_agenda` decide también qué texto propone cambiar el constructor
  (`agenda_text.py`, `agent_draft.py`): el arreglo cambia esas propuestas igual.
- La revisión no bloquea con `contradicts_business` ni con `forbids_agenda` (son `warn`):
  el arreglo no cambia lo que se puede publicar.

## Open Questions

- Ninguna que bloquee.
