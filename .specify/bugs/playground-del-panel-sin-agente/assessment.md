# Bug Assessment: el Playground del panel prueba el agente sin sus conectores

- **Slug**: playground-del-panel-sin-agente
- **Created**: 2026-11-16
- **Source**: prueba en staging del conector de Quédate (spec 061), cliente «Prueba Quédate 061», partner «Demo (staging)»
- **Verdict**: valid
- **Severity**: high — en todo cliente de la consola nueva, el Playground del panel no puede probar ninguna herramienta de conector

## Report (verbatim or summarized)

El agente de prueba del cliente «Prueba Quédate 061» no recibía ninguna herramienta
en el Playground del panel. Comprobado en staging el 2026-11-16 llamando a
`activations.tool_policy` a mano: con el `agent_id` real del agente, 0 de las 27
herramientas de Quédate quedan bloqueadas; con `None`, las 27.

## Symptom

En un cliente cuyo partner tiene la consola nueva (`partner_on_v2`), un turno del
Playground del panel (`/qa/{cliente}/chat` y la pestaña Playground del cliente) no
ofrece al modelo ninguna herramienta de conector, aunque el agente tenga la
activación. Lo esperado es que el Playground pruebe el agente con lo mismo que
tendría en su canal.

Dos síntomas más en la misma superficie:

- La insignia «Dry run» del encabezado está escrita a mano: sale también en un hilo
  en vivo (`dry_run = false`). El tipo `QAThread` del panel ni siquiera trae
  `dry_run`.
- Con varios agentes, el panel no deja elegir cuál se prueba. Siempre contesta el
  principal y el encabezado enseña la versión del principal. La spec 030 (R14.5)
  pide que «cada pantalla que hoy edita "el agente" DEBE dejar elegir cuál».

## Reproduction

1. Un cliente de un partner con `console_v2_enabled_at`, con un agente activo que
   tiene un conector conectado y activado (`agent_connector_activations`).
2. Abrir el Playground del panel y mandar un mensaje.
3. El estado del turno llega al grafo sin `agent_id`. `_load_tool_policy(tenant, None)`
   no encuentra la activación del agente y, en la consola nueva, bloquea todas las
   herramientas de conector.

## Suspected Code Paths

- `apps/api/src/nexus_api/api/qa.py:708` (`_run_in_process`, el `/send`) y
  `qa.py:1041` (`start_thread_run`, el `/runs` que usa el panel): los dos `state`
  llevan `tenant_id`, `channel_id`, `user_id`, `conversation_id` y `customer_id`,
  pero no `agent_id`.
- `qa.py:105` (`ThreadCreate`) y `qa.py:231`: el hilo del panel nace con
  `agent_id = NULL`. La columna existe desde la spec 030 (`QAThread.agent_id`) y la
  consola del partner ya la rellena.
- `apps/worker/src/nexus_worker/runtime/pipeline.py:1923`: la política se calcula con
  `_agent_uuid(state)`. Sin `agent_id` en el estado da `None`.
- `apps/api/src/nexus_api/services/activations.py:134` (`tool_policy`): sin agente
  no hay activaciones y, con `strict` (consola nueva), todo lo de conector queda
  bloqueado.
- `apps/api/src/nexus_api/api/console/playground.py:561`: la consola sí pasa
  `agent_id`, pero solo cuando el hilo lo tiene. Un hilo suyo de antes de la spec 030
  (`agent_id` NULL) cae en el mismo bloqueo.
- `apps/admin/src/components/qa/playground-shell.tsx`: la insignia fija y la falta
  de selector.

## Root Cause Hypothesis

El Playground del panel es anterior a los agentes por cliente (spec 030) y nunca
pasó a fijar un agente por hilo. Hasta la spec 047 no se notaba: el cargador
(`AgentLoader.load(tenant, None)`) devuelve el principal, así que el prompt y la
lista blanca eran los correctos. Desde la política de activaciones de la 047, «sin
agente» significa «sin activación», y en la consola nueva eso cierra los
conectores. Confianza alta: reproducido en staging con `tool_policy` y confirmado
en el código.

## Proposed Remediation

**Preferred**: que el hilo fije su agente, como en la consola (spec 030), y que el
estado del turno lo lleve siempre.

- `POST /qa/threads` acepta un `agent_id` opcional. Tiene que ser un agente activo de
  ese cliente; se comprueba bajo su RLS y además por `tenant_id`, como
  `console/deps.agent_scope`. Si no, 404. Sin `agent_id`, el hilo nace con el
  principal.
- Al correr un turno (`/send` y `/runs` en el panel, y `start_run` en la consola), el
  agente es el del hilo. Un hilo con `agent_id` NULL (todos los del panel hasta hoy)
  resuelve el principal y **lo deja sellado en el hilo**, para que una conversación
  de pruebas no cambie de agente a mitad. Un único constructor del estado para los
  tres caminos, para que no vuelvan a divergir.
- `ThreadOut` expone `agent_id`.
- Panel: el Playground lee `?agent=`, igual que la pestaña Agente. Enseña el
  selector cuando hay más de un agente, lista los hilos de ese agente (los NULL
  cuentan como del principal) y crea los nuevos con él. El encabezado enseña el
  nombre y la versión de ese agente.
- La insignia sale del `dry_run` del hilo activo: «Dry run» o «En vivo».

**Alternatives**:
- Usar `bundle.agent_id` en `pipeline.py:1923` cuando el estado no trae agente.
  Arreglaría el síntoma para todos los caminos, pero cambia una decisión de la
  spec 047: la política cerrada sin agente es deliberada (65.11), y el dispatcher
  siempre nombra el agente. Se descarta: el arreglo va donde falta el dato.
- Usar el agente del canal web del QA (`Channel.agent_id`). Ese canal es uno por
  cliente, así que con varios agentes no permite probar más que uno. Se descarta.

**Files likely to change**:
- `apps/api/src/nexus_api/api/qa.py`
- `apps/api/src/nexus_api/api/console/playground.py`
- `apps/admin/src/lib/qa-api.ts`
- `apps/admin/src/components/qa/playground-shell.tsx`
- `apps/admin/src/components/qa/thread-list.tsx` (solo si hace falta)
- `apps/admin/src/app/(dashboard)/qa/[tenantId]/chat/page.tsx`
- `apps/admin/src/app/(dashboard)/tenants/[id]/playground/page.tsx`
- `apps/admin/src/app/(dashboard)/tenants/[id]/agent/agent-picker.tsx` (que pueda
  ocultar «Nuevo agente»)

**Tests to add or update**:
- Integración, por los endpoints y con el pipeline sustituido por uno que captura
  el estado: en un cliente de la consola nueva con un conector activado, el estado de
  `/runs` y el de `/send` llevan el agente, y `_load_tool_policy` con ese estado no
  bloquea sus herramientas. En rojo antes del arreglo: el estado no trae agente y se
  bloquean todas.
- Un hilo viejo (`agent_id` NULL) corre con el principal y queda sellado.
- Un hilo creado con otro agente del cliente corre con ese agente.
- Aislamiento: `POST /qa/threads` con el agente de otro cliente da 404 y no crea
  hilo.
- Panel: la insignia sigue al `dry_run` del hilo, y el hilo nuevo lleva el agente
  elegido.

## Risks & Considerations

- `principal_agent_id` no filtra por cliente: depende de la RLS. Hay que llamarlo
  dentro de la transacción, después de `apply_tenant_to_session`.
- Un `agent_id` que viene del navegador es entrada no confiable y la columna no
  tiene FK. La comprobación es por RLS **y** por `tenant_id`. Toca el aislamiento:
  pasa `/cso`.
- Sellar el principal en los hilos NULL cambia filas existentes de `qa.threads`. Es
  lo que dice el modelo («NULL = el principal») hecho explícito, y solo pasa al
  correr un turno.

## Open Questions

- **Crear un hilo en vivo desde el panel (ADR-024).** Hoy solo se puede por la API
  (`POST /qa/threads` con `dry_run: false` o `PATCH`). Es funcionalidad nueva y abre
  una frontera de confianza: un turno en vivo toca los conectores reales del
  cliente. El ADR-024 no está en el repo, solo citado en comentarios. No entra en
  este arreglo; queda como propuesta de spec.
- **Una escalada de un hilo que se arrastra a los siguientes hilos del mismo
  operador.** En staging pareció pasar; sin verificar. Se investiga aparte. El
  resultado queda en `fix.md`.
