# Agentes: AgentSpec, constructor, pruebas, puerta, estados y versiones

Spec 047 («La fábrica de agentes»). Este documento cuenta cómo nace, se prueba, se
publica y vive un agente en la consola nueva, y dónde está cada pieza. El detalle
de cada regla está en `specs/047-la-fabrica-de-agentes/` (requisitos 15 a 27 y 33
a 42).

## 1. El AgentSpec

Cada versión de un agente (`agent_configs`) guarda su **AgentSpec**
(`agent_configs.spec`, `services/agent_spec/schema.py`) y el prompt se compila de
él (`services/agent_spec/compiler.compile_spec`). Mismas entradas, mismos bytes.

- **Dos modos.** «structured» (lo que hace el constructor: identidad, objetivo,
  secciones, reglas, herramientas, escalada, voz, preguntas frecuentes) e
  «instructions» (los agentes de antes: su prompt de hoy, byte a byte). La
  migración 0189 pasó cada prompt propio a «instructions»
  (`services/agent_spec/legacy.spec_from_version`); el ensayo de la consola nueva
  comprueba que sigue compilando los mismos bytes (sección 7).
- **Validador** (`services/agent_spec/validator.py`): errores que bloquean la
  puerta (herramientas desconocidas, límites, coherencia con la ficha) y avisos.
- **Revisión** (`services/agent_spec/review.py`, `api/console/agent_review.py`):
  incoherencias como prometer algo sin la herramienta que lo hace; las
  bloqueantes paran la puerta.

## 2. El constructor

Todo lo largo es un **trabajo** (`jobs`, `services/jobs.py`) que corre el worker
(`wk/jobs/handlers/*`) y la consola sigue por `GET /console/jobs/{id}`.

- **Borrador** (`services/builder/agent_draft.py`, `POST
  /console/clients/{ref}/agents/draft-jobs`): «Generar borrador», «Desde una
  plantilla» o «En blanco». Lee la ficha del negocio y devuelve un AgentSpec, sus
  preguntas abiertas, las integraciones que necesita y su batería de pruebas.
- **Copiloto** (`services/builder/copilot.py`): propone cambios como
  **propuestas** (`proposals`) con su diff; aceptar es aplicarlas al borrador.
- **Partida «Construcción y pruebas»**: todo el constructor, las pruebas y el
  playground cuentan en ella y se paran al agotarla (`402
  build_budget_exhausted`; ver `docs/billing.md`). La edición a mano sigue.

## 3. Pruebas

- **Batería por agente** (`agent_test_suites`, `agent_tests`;
  `services/testing/suites.py`): pruebas «case» con su primer mensaje, su plan, el
  estado esperado y sus criterios; las **críticas** tienen que pasar 3 de 3.
- **Catálogo del sector** (`sector_test_catalog`, 12 por sector, editable en el
  admin) y el **juez** (`services/testing/judge.py`), calibrado desde el admin.
- **Pasadas** (`agent_test_runs`, `services/testing/runs.py`): todas, las
  afectadas o una; un cambio de la ficha deja desactualizadas las afectadas y las
  vuelve a pasar en segundo plano en los agentes publicados
  (`business/writes.mark_tests_stale`). Si esa pasada deja pruebas en rojo, el
  partner recibe `agent.tests.failing` (una vez por agente y día,
  `wk/jobs/handlers/agent_tests.tell_failing`, requisito 13.7).
- **Playground** (`api/console/agent_playground.py`): sobre el borrador o una
  versión, con hora y agenda simuladas; el «cliente» lo escribe la propia persona
  del partner.

## 4. La puerta

`services/publishing.py`. Publica solo si:

1. el validador da 0 errores;
2. las pruebas críticas pasan 3 de 3;
3. la tasa global no baja más de 2 puntos frente a la versión activa;
4. el aviso de IA está decidido;
5. la revisión no tiene bloqueantes;
6. si la versión cambia de modelo o de calidad, ese cambio está comprobado
   (`model_policy_unchecked`, sección 6).

El aviso de IA lo decide una persona en la pantalla del agente, en su bloque
«Aviso de IA» (en el primer mensaje de cada conversación o solo si le preguntan,
con sus palabras opcionales); «Arreglar en el borrador» del hallazgo lo abre. El
constructor no lo deja decidido (16.6).

El validador y el aviso de IA no se saltan nunca. Una prueba normal en rojo deja
«Guardar igualmente»; una crítica, la regresión o un bloqueante solo los salta un
owner, un admin o Auphere, con motivo (queda en la versión y en la auditoría). La
usan los tres sitios que publican: la consola, el admin y la API de partners. Cada
decisión deja el evento `gate.decision` (`outcome`: `published`, `blocked`;
`blocking`: los códigos).

**Después de publicar**: el siguiente mensaje usa la versión nueva; hay 10 minutos
para deshacer; restaurar una versión la trae como borrador y vuelve a pasar la
puerta.

## 5. Estados

Lo que se guarda (`agents.lifecycle`): `draft`, `published`, `paused` con motivo
(`manual`, `no_balance`, `agent_cap`, `client_paused`, `client_archived`) y
`archived`. Lo que se enseña se deriva en un solo sitio
(`services/agent_lifecycle.py`) y lo leen la consola, la lite, la app y el Panel:
`archived`, `paused`, `draft`, `serving` («Atendiendo»), `testing` («En prueba»)
y `ready_no_channel` («Listo · sin canal»). Un canal en pausa o con problemas no
cuenta como canal que atiende.

- Pausar y reanudar: `services/agent_states.py`. Las pausas del sistema
  (`no_balance`, `agent_cap`) las quita el sistema (al volver el saldo, al subir el
  tope o el día 1); las de una persona, solo una persona.
- La regla única de «necesita atención» (`services/attention.py`) la usan la lista
  de clientes, el Panel del partner y ⌘K.

## 6. Calidad y modelo

`services/agent_quality.py` y `api/console/agent_quality.py`: el precio por
mensaje de cada perfil de calidad (a precio, coste × 2,2), los modelos que se
pueden fijar según la UE, lo soberano y lo que permite el partner, y «Comprobar
este cambio» (una pasada de certificación con la política nueva). El router y el
catálogo están en `docs/modelos-y-router.md`.

## 7. Conocimiento, integraciones y memoria

- **Capas** (`services/knowledge/`): la del negocio (`agent_id` NULL) la ven todos
  los agentes del cliente; la de un agente, solo él. Búsqueda híbrida exacta
  (texto y vectores `halfvec(1024)` en `knowledge_chunk_vectors`, RRF k=60).
  «Enseñar» (`teach.py`) escribe en la capa que se elija y vuelve a pasar las
  pruebas de quien lo ve. Las fuentes de cada respuesta quedan en `turn_sources`.
- **Activaciones** (`services/activations.py`): una conexión por cliente y una
  activación por agente con su permiso (`read`, `ask_before_write`,
  `read_write`). El turno solo ve las herramientas de sus activaciones;
  «Preguntar antes de escribir» pide permiso al dueño (`tool_approvals.py`).
- **Memoria del contacto**: por agente (`agent_memories.agent_id`).

## 8. La consola nueva, partner a partner

`services/console_v2.py` y `api/admin/console_v2.py`. Auphere activa la consola
nueva para cada partner tras un **ensayo** limpio (24 h): por agente, el prompt
compila los mismos bytes y el modelo sigue fijado; por número, la audiencia
efectiva es la misma con las reglas de hoy y con las nuevas. Una diferencia
bloquea la activación. Desactivar devuelve la consola de hoy hasta que el
partner confirma el reparto en bolsas. Los informes quedan en
`migration_reports`.
