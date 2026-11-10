# Bug Assessment: las habilidades encendidas se pierden al editar las instrucciones

- **Slug**: las-habilidades-encendidas-se-pierden-al-editar
- **Created**: 2026-11-08
- **Source**: certificación en staging (2026-11-08), agente Ana de Jemma's Hair
- **Verdict**: valid
- **Severity**: high (el agente pierde sin aviso lo que se le encendió; la revisión dice
  que no tiene herramientas que sí tiene)

## Report (verbatim or summarized)

A Ana (agente de instrucciones libres, de antes de la 047) se le encendieron en
Habilidades seis herramientas de Reservas: `answer_offer`, `cancel`,
`confirm_attendance`, `join_waitlist`, `reschedule` y `list_mine`. La página de
Habilidades dice «18 active». La ficha del agente, en el mismo borrador, dice «12
skills on», y la revisión avisa: «Las instrucciones prometen cambiar o cancelar citas y
el agente no tiene ninguna herramienta que lo haga».

## Symptom

- La ficha y la revisión no ven lo que se encendió en Habilidades.
- La siguiente edición de la spec (instrucciones, reglas, una propuesta del copiloto o
  «Fix») borra del borrador lo que se encendió, sin avisar. Publicado así, el agente
  deja de poder hacerlo.

## Reproduction

1. Un agente con `spec.mode == "instructions"` guardado y tres herramientas.
2. Encender `reservas.cancel` en Habilidades (`PUT /console/clients/{ref}/capabilities`).
3. `GET …/agents/{id}/draft`: `spec.tools` no tiene `reservas.cancel`.
4. Guardar las instrucciones (`PATCH …/draft` con la spec que la consola leyó):
   `agent_configs.tools` del borrador ya no tiene `reservas.cancel`.

Reproducido en `apps/api/tests/integration/test_skills_survive_an_instructions_edit.py`
(dos pruebas en rojo antes del arreglo).

## Suspected Code Paths

- `apps/api/src/nexus_api/api/console/capabilities_client.py` — `update_capability`:
  en un agente que no es estructurado escribe `draft.tools` y no la spec.
- `apps/api/src/nexus_api/api/console/agent_spec_drafts.py` — `spec_of` devolvía la
  spec guardada tal cual, con la lista de herramientas de la última edición; y
  `write_spec`, en modo instrucciones, deja `draft.tools` = lo que no tiene forma de
  catálogo + `spec.tools`.

## Root Cause Hypothesis

En un agente de instrucciones hay dos listas: la de la versión (`agent_configs.tools`,
la que construye el runtime y la que escriben los interruptores) y la copia de la spec.
Las lecturas usaban la copia, que se queda vieja en cuanto se enciende algo, y la
escritura de la spec la volvía a imponer. Confianza: **alta** (reproducido).

Un agente sin spec guardada no lo sufre: `spec_from_version` ya lee las herramientas
de la versión. Un agente estructurado tampoco: sus interruptores escriben la spec
(`_set_spec_tool`).

## Proposed Remediation

**Preferred**: que `spec_of`, en modo instrucciones, lea las herramientas de la
versión, como ya hace `spec_from_version`: lo de la versión que la spec ya nombraba
(aunque no tenga la forma del catálogo, como las de Google que esperan pasar a
Reservas) y lo que tiene la forma del catálogo, en el orden de la versión y con el
tope de 60 del esquema. Con eso la ficha, la revisión, la puerta de publicar y la
edición ven lo mismo que el runtime, y la edición manda de vuelta lo encendido.

**Alternative**: que el interruptor escriba también la spec de un agente de
instrucciones. Descartada como única medida: no arregla los borradores que ya están
desfasados (el de Ana).

## Test plan

- `test_a_switched_on_skill_is_in_the_spec_the_console_reads`: tras encender,
  `GET …/draft` trae la herramienta en `spec.tools`.
- `test_editing_the_instructions_keeps_the_skills_switched_on`: tras encender y
  editar las instrucciones, el borrador conserva la herramienta.
- Sin regresión: constructor, habilidades, publicación, recepción, reservas manda,
  mejoras, conectores y aislamiento de consola.
