# Bug Assessment: aceptar una pregunta frecuente del constructor la deja sugerida

- **Slug**: aceptar-una-faq-la-deja-sugerida
- **Created**: 2026-11-26
- **Source**: pasted text (sesión principal de la beta de Jemma, 2026-11-26; nota de KB `research/2026-11-26-beta-jemma-p0-p1.md`, sección 081, B1). Sin URL.
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

> El constructor guarda la propuesta como `{"q","a","suggested": True}`
> (`client_profile.py:307`). «Aceptar» aplica `row.proposed_value` tal cual
> (`suggestions.py:131-152`). `faqs._apply` pasa `suggested=True` a `create_faq`
> (`faqs.py:213-221`). La FAQ queda fuera del prompt (`compilation.py:243`) y reaparece
> en «Por confirmar» (`faqs-section.tsx:76,179-189`), mientras el aviso dice «Añadido a la
> ficha» (`suggestion-card.tsx:68`). Luis confirmó que es exactamente lo que ve. Ninguna
> prueba cubre «aceptar una FAQ».

## Symptom

En Negocio › Preguntas frecuentes, «Aceptar» sobre una pregunta que propuso el constructor
avisa «Añadido a la ficha», pero la pregunta vuelve a salir en «Por confirmar» y ningún
agente la usa. Lo esperado: aceptada por una persona, la pregunta queda confirmada, sale en
la lista de confirmadas y entra en el prompt de todos los agentes del cliente.

## Reproduction

1. Lanzar el constructor del cliente (`client_builder`), con o sin modelo: propone
   preguntas frecuentes en `business_suggestions` con `pointer = "/faqs/-"` y
   `proposed_value = {"q", "a", "suggested": true}`.
2. `POST /console/clients/{ref}/business/suggestions/{id}/decide` con
   `{"decision": "accept"}`.
3. `business_faqs` tiene la fila con `suggested = true`.
4. `GET …/business/faqs` la devuelve con `suggested: true`; la consola la pinta en «Por
   confirmar» con su tarjeta de sugerencia.
5. El `system_prompt_rendered` de la versión activa no la lleva: `load_facts` descarta las
   sugeridas.

«Editar» no falla: la consola manda `{q, a}` sin `suggested` y la fila queda confirmada.
Por eso la prueba que existe (que edita una y descarta las demás) pasa.

## Suspected Code Paths

- `apps/api/src/nexus_api/services/builder/client_profile.py:307` — la propuesta lleva
  `suggested: True` desde la spec 047 (`32bfcb8b`): la marca «Sugerido · confirma» del
  requisito 18.3 se escribió dentro del valor propuesto.
- `apps/api/src/nexus_api/services/business/suggestions.py:131` — `accept` aplica
  `row.proposed_value` tal cual, con `review="confirmed"`.
- `apps/api/src/nexus_api/services/business/faqs.py:218` — `_apply` copia
  `value["suggested"]` a la fila nueva.
- `apps/api/src/nexus_api/services/business/compilation.py:243` — el prompt deja fuera las
  sugeridas (correcto: es el requisito 18.3).
- `apps/console/src/components/business/sections/faqs-section.tsx:76` — «Por confirmar»
  enseña las guardadas como sugeridas (correcto, también).
- `apps/api/tests/integration/builder/test_client_builder_and_copilot.py:93` — la prueba
  fija la forma `proposed_value["suggested"] is True` y nunca acepta una pregunta.

## Root Cause Hypothesis

Confianza alta. Hay dos marcas para lo mismo: la fila de `business_suggestions` (sin
decidir = por confirmar) y `business_faqs.suggested`. El constructor puso las dos, y la
decisión de una persona solo apaga la primera. Nadie más crea filas con
`suggested = true`: el lector (`reader.py:1124`), las correcciones, los arreglos del
constructor y el alta a mano crean confirmadas; solo «aceptar» una propuesta del
constructor, importar un ClientSpec que traiga `suggested: true` y deshacer a un estado que
la tuviera la dejan sugerida.

## Proposed Remediation

**Preferred**: al decidir una persona (aceptar o editar) una propuesta de `/faqs/…`, el valor
que se aplica no lleva `suggested`: decidir es confirmar. Se hace en `suggestions.decide`,
que es quien sabe que decidió una persona, y no en `faqs._apply`, que también sirve para
deshacer (ahí `suggested` debe volver como estaba). No se cambia la forma de lo que propone
el constructor: hay filas pendientes en prod con `suggested: true`, y `_open_same` y
`_discarded_same` comparan el JSON exacto, así que cambiar la forma dejaría volver lo
descartado. (La spec 081 cambia esa deduplicación por la pregunta normalizada; entonces se
puede limpiar la forma.)

**Las ya guardadas por este fallo**: no se tocan con una migración. Una migración en SQL no
sube `content_rev` ni recompila (la 0186 lo deja escrito: una migración no importa código
de la aplicación ni recompila), así que la ficha diría «confirmada» y el prompt seguiría sin
ella hasta la siguiente escritura. Siguen en «Por confirmar» y su «Aceptar» ya las confirma
(`decideSaved` → `PATCH …/faqs/{id}` con `suggested: false`, que pasa por
`section_write` y recompila). La prueba lo fija. El informe da la consulta de solo lectura
para contarlas en prod.

**Alternatives**:
- Migración que las confirma por el `/faqs/-` aceptado de su cliente: deja ficha y prompt
  distintos hasta la siguiente escritura de cada cliente; descartada.
- Quitar `suggested` en `faqs._apply` cuando `review == "confirmed"`: también afectaría a
  deshacer; descartada.

**Files likely to change**:
- `apps/api/src/nexus_api/services/business/suggestions.py`
- `apps/api/tests/integration/builder/test_client_builder_and_copilot.py` (o una prueba
  nueva junto a ella)

**Tests to add or update**:
- Aceptar una pregunta del constructor: la fila queda `suggested = false`, `GET …/faqs` la
  devuelve confirmada, ninguna sugerencia queda pendiente y el prompt de la versión activa
  la lleva.
- Editar sigue confirmando.
- Una guardada como sugerida (la forma que dejó el fallo) se confirma con
  `PATCH {"suggested": false}` y entra en el prompt.
- Deshacer después de aceptar no rompe nada (sigue funcionando el adaptador).

## Risks & Considerations

- Confirmar una pregunta cambia el prompt de todos los agentes activos del cliente (es lo
  que se pidió). Las pruebas de cada agente quedan desactualizadas, como con cualquier
  escritura de la ficha.
- Importar un ClientSpec con `suggested: true` y aceptarlo también la confirma: aceptar es
  decisión de una persona.

## Open Questions

- Ninguna que bloquee. Cuántas hay en prod se cuenta con la consulta del informe.
