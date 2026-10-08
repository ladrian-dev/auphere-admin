# Implementation Plan: la consola lite — el cliente final entra en la misma consola

**Branch**: `030-consola-lite-del-cliente` | **Date**: 2026-10-08 | **Spec**: [spec.md](spec.md)

**Input**: `specs/030-consola-lite-del-cliente/spec.md` · diseño «Consola Lite.dc.html» · [ADR-041](../../../../Work/Auphere/nexus/decisions/ADR-041-consola-lite-del-cliente-final.md)

## Summary

Un segundo tipo de persona entra en la consola: el **usuario de cliente**,
atado a un solo cliente (tenant) de un partner, con los módulos de su cliente
como único permiso. Vive en **tablas propias** (`client_memberships`,
`client_invitations`) y se autoriza con **su propia dependencia**
(`require_client_principal`), de modo que todas las rutas del partner quedan
cerradas para él sin tocarlas —`require_console_principal` solo mira
`partner_memberships`— y todas las suyas, bajo `/console/lite/*`, cerradas
para el partner. El cliente sale de su acceso, nunca de la petición: las rutas
lite no tienen `{ref}`.

Panel y Consumo lite llaman a **las mismas funciones** que la consola del
partner con un único cliente, para que las cifras coincidan al céntimo
(CE-003). La Bandeja es lo único nuevo: reutiliza la lógica de toma de control
del admin (extraída a un servicio común), arregla el ciclo de vida de la
conversación (el escalado ya no parte el hilo, «resuelta» existe y se reabre
sola) y añade lectura por persona, etiquetas, notas, respuestas guardadas,
archivos en los dos sentidos y tiempo real por SSE. El multiagente convierte
«el agente del cliente» en **una tabla de agentes** con versiones por agente y
**cada número asignado a un agente**: el enrutado sale del número, sin
clasificador.

Tres iteraciones, cada una entregable sola y en orden de superficie:

1. **La puerta y lo que ya existe** — acceso desde el admin, identidad de
   cliente, consola lite, Panel y Consumo de un cliente. (H1–H4)
2. **La Bandeja** — con un agente. (H5–H10, H12)
3. **Varios agentes** — modelo, runtime, configuración y lo que la Bandeja,
   el Panel y el Consumo enseñan por agente. (H11)

## Technical Context

**Language/Version**: Python 3.14 (API, worker, MCP) · TypeScript 5 / Next.js 16.2 / React 19.2 (consola y admin)
**Primary Dependencies**: FastAPI · SQLAlchemy async · Alembic · sse-starlette · Dramatiq · Redis · S3 (todo ya instalado) · `@nexus/ui` (base-ui, cva, recharts) en la consola · shadcn propio en el admin — **ninguna dependencia nueva**
**Storage**: Postgres (RLS forzada por `app.tenant_id`), Redis (pub/sub y anti-replay), S3 (archivos de conversación). Migraciones **0147–0153** (ver [data-model.md](data-model.md))
**Testing**: pytest (`apps/api/tests/{unit,integration,isolation}`, `apps/worker/tests`, `apps/mcp/tests`) · vitest (consola, admin, `@nexus/ui`) · Playwright + axe en la consola
**Target Platform**: AWS (ECS) para API/worker; Vercel para consola y admin
**Project Type**: web — monorepo con API, worker, MCP, dos apps Next.js y un paquete de UI
**Performance Goals**: primera página de la Bandeja < 1,5 s p95 con 5.000 conversaciones (CE-007) · mensaje nuevo visible < 5 s (CE-004) · Panel lite < 1 s p95
**Constraints**: el cliente nunca es argumento · rutas de cuerpos de mensaje separadas (C8) · nunca nuestro coste (C9) · sin hex ni valores fuera de escala (`@nexus/ui/eslint`) · ES/EN · claro/oscuro · WCAG 2.2 AA · 360 px sin desbordes
**Scale/Scope**: decenas de clientes con acceso al principio; por cliente, miles de conversaciones y pocas personas (1–10)

## Constitution Check

*Rellenado antes de la Fase 0 y comprobado de nuevo tras el diseño: sigue en verde.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | El tenant del usuario de cliente sale de `client_memberships` y se fija con `apply_tenant_to_session`; las rutas lite no aceptan `ref`, `tenant_id` ni `partner_id`. Tablas nuevas con RLS `ENABLE`+`FORCE`. Lista blanca por agente. Barridos nuevos: `tests/isolation/test_lite_route_scope.py`, `test_lite_client_vs_client.py`, `test_lite_bodies_only_in_inbox.py`, `test_agent_scope_within_tenant.py`, `test_contact_notes_never_reach_agent.py` (D18) |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie `0`, ya abierta. Iteraciones en orden: lo que reutiliza, luego lo nuevo, luego el runtime |
| III | Lo leído es dato, nunca instrucción | ☑ | Las notas internas no llegan nunca al agente (barrido). Los mensajes de una persona entran en el historial como hoy los del operador. Nada leído cambia permisos |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Las acciones de la Bandeja las hace una persona en su nombre: no hay agente actuando, así que no hay aprobación que pedir. La auditoría nombra a la persona (`client:<correo>`) y al operador del admin (`operator:<correo>`, nunca el prefijo del token) |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | Cada bloque lite pinta cargando/vacío/error/parcial; la Bandeja añade `reconectando` (SSE caído → sondeo) y `bloqueado` (ventana de 24 h cerrada, número desconectado, tope agotado). Sin Bandeja, sin agentes plurales, sin canales plurales: no se pinta nada (D14) |
| VI | Por API `console.*`, nunca navegando la consola | ☑ | Todo es API; el Companion no gana herramientas lite |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada tarea empieza por su test en rojo; los barridos de aislamiento no se saltan |
| VIII | Licencias leídas enteras | ☑ | Ninguna dependencia nueva |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[ADR-041-consola-lite-del-cliente-final]]`, enlazada desde la spec y desde el índice de ADRs |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Garantías **1, 2, 4, 5, 8** y dos ejes nuevos: cliente ↔ cliente del mismo partner, y partner ↔ cuerpos de mensaje | Un test por garantía y eje en `apps/api/tests/isolation/` (ver tasks) |
| **Licencias** | Ninguna dependencia nueva | — (comprobado en la revisión del diff) |
| **Medidor** | Nada nuevo que gaste: sin llamadas nuevas al modelo. Los mensajes de la Bandeja ya se miden como mensaje saliente. El medidor gana la dimensión **agente** (`usage_records.agent_id`, `usage_ledger.agent_id`) | Tareas de la iteración 3 |

## Decisiones

### Identidad y acceso (iteración 1)

- **D1 · Tablas propias para el usuario de cliente.** `client_memberships`
  (cuenta ↔ partner + tenant) y `client_invitations`, en vez de un rol más en
  `partner_memberships`. Hoy hay código que recorre los miembros de un partner
  (Equipo, correos de avisos, límites de plazas): con un rol nuevo, cada uno
  de esos sitios tendría que acordarse de excluirlo, y el que se olvide filtra.
  Con tabla propia, lo que existe sigue siendo correcto sin tocarlo. Una cuenta
  es de una de las dos tablas, nunca de las dos: lo comprueba la invitación y
  la aceptación, bajo bloqueo consultivo por correo, y lo fija un test.
- **D2 · Dependencia propia.** `require_client_principal(*modules)` devuelve un
  `ClientPrincipal` (cuenta, partner, membresía, `tenant_id`, `client_ref`,
  nombre del cliente, módulos). Comprueba: firma y anti-replay (igual que hoy),
  membresía activa, acceso del cliente activo, partner `active`, tenant no
  archivado, y el módulo pedido. **No** exige `partners.console_enabled`: ese
  interruptor es de la consola del partner. Fija el tenant en la sesión.
  `actor` = `client:<correo>`.
- **D3 · El mismo token.** El BFF acuña `{sub, partner_id, role: "client"}` con
  la misma clave y vida. La API decide por la tabla donde está la cuenta, no por
  el claim, así que un claim cambiado no abre nada.
- **D4 · La sesión distingue.** `load_principal_view` busca primero en
  `partner_memberships` y, si no hay fila, en `client_memberships`.
  `PrincipalOut` gana `kind` (`partner` | `client`), `client_name`, `modules` y
  conserva `partner_name` (a quién pedir saldo). Acceso del cliente apagado →
  `access = "disabled"`; persona revocada → `"suspended"`.
- **D5 · Rutas lite.** Todo lo del cliente cuelga de `/console/lite/*` y la
  Bandeja de `/console/lite/inbox/*`, las **únicas** rutas de la consola que
  pueden devolver cuerpos de mensaje. Ninguna lleva `{ref}`. Contratos en
  [contracts/lite-api.md](contracts/lite-api.md).
- **D6 · Admin.** Pestaña «Acceso» en la ficha del tenant del admin (patrón de
  `runtime-capabilities.tsx`: filas con casilla y «Guardar» con diff) y lista de
  personas con invitar, reenviar y revocar (patrón `react-hook-form` + `zod` +
  acción de servidor). Endpoints en
  [contracts/admin-api.md](contracts/admin-api.md). La auditoría lleva la
  identidad del operador de la sesión del admin (ADR-034, `X-Operator-Id`), no el
  prefijo del token: sin operador identificado, 401.
- **D7 · Invitación y entrada.** La invitación de cliente usa la misma página
  `/invite/[token]` de la consola; el endpoint de servicio busca el hash en las
  dos tablas de invitaciones. Aceptar crea la cuenta (o pide la contraseña de la
  existente) y la membresía de cliente. Recuperar contraseña (spec 011) ya es
  por cuenta: no cambia. Revocar o apagar el acceso termina las sesiones con la
  misma función que usa el canje de la spec 011.

### Panel y Consumo de un cliente (iteración 1)

- **D8 · Las mismas funciones, un cliente.** Los cálculos de `home.py`,
  `console_home_blocks.py`, `usage.py` y `metering/wallet.py` que hoy reciben
  la lista de clientes del partner se llaman con `[tenant_id]`. Donde la lógica
  vive dentro del endpoint, se extrae a un servicio y el endpoint del partner
  pasa a llamarlo (sin cambiar su respuesta: lo fija su test actual). Lo que es
  del partner entero —saldo del partner, gasto fuera de clientes, alertas— no
  se calcula para el cliente.
- **D9 · Saldo del cliente** = lo que le queda de su tope (`remaining` de su
  asignación) y para cuántos días alcanza con su gasto de los últimos 7 días.
  Sin asignación → «sin tope asignado», nunca un cero. **Depende del arreglo del
  doble débito** (propuesto como sesión aparte); hasta entonces Consumo lite no
  se abre a un cliente real.
- **D10 · A quién pedir saldo.** Cliente de un partner → el nombre del partner.
  Cliente de Auphere Internal Partner → «Auphere». Se decide en servidor y
  viaja en `/console/lite/me`.

### La Bandeja (iteración 2)

- **D11 · Una conversación por contacto y número.** El alta de conversación del
  worker deja de buscar solo `OPEN`: toma la **última** fila de ese contacto en
  ese número, sea cual sea su estado. `ESCALATED` sigue en la misma fila (el
  hilo ya no se parte, tenga o no Bandeja el cliente). `CLOSED` («resuelta») se
  reabre a `OPEN` con un evento. Como hoy nadie escribe `CLOSED`, el único
  cambio de comportamiento para quien no tiene Bandeja es que el escalado ya no
  deja huérfana la conversación.
- **D12 · Estados de la Bandeja**, derivados sin columnas nuevas de estado:
  *espera a una persona* = `ESCALATED`; *responde una persona* =
  `agent_active = false` y `assigned_user_id` presente; *responde el agente* =
  `agent_active = true`; *resuelta* = `CLOSED`. Tomar el control o devolverla
  pasan `ESCALATED` a `OPEN`.
- **D13 · El escalado, en un solo sitio.** `services/inbox_lifecycle.py`
  (`mark_waiting`) lo llama la herramienta `escalate.escalate_to_human`, que es
  la única que escribe `ESCALATED`: deja el evento con motivo y resumen y, **si
  el cliente tiene Bandeja** (`client_access.enabled` y `'inbox' = ANY(modules)`),
  silencia al agente (`agent_active = false`,
  `takeover_context.reason = "escalated"`), publica el evento en tiempo real y
  avisa a las personas del cliente (campana y correo, una vez por escalado).
  Sin Bandeja, solo el evento: el agente sigue como hoy. Quitar la Bandeja o
  apagar el acceso devuelve al agente las conversaciones silenciadas por
  escalado (`release_escalated_for_tenant`), con evento.
- **D14 · La toma de control, en un solo sitio.** La lógica del admin
  (`If-Match` sobre `agent_active_version`, `takeover_context`, auditoría,
  evento) se extrae a `services/conversation_control.py` con el actor como
  parámetro; el admin y la lite la usan. Devolver deja el `takeover_context` para
  que el despachador arme el resumen de lo que hizo la persona (como hoy).
- **D15 · Enviar.** Texto y adjuntos solo si la conversación la atiende **quien
  envía** (tomar el control la reasigna, con `If-Match`), si la ventana de 24 h
  está abierta (`last_inbound_at`) y si el número está conectado. El mensaje es
  `actor_kind = "member"` con `actor_id` = cuenta. Adjuntos: JPEG y PNG hasta
  5 MB, PDF hasta 16 MB (dentro de lo que WhatsApp admite), a S3 con
  `MediaStorage.put_outbound` —que existe sin llamante— y salen por el
  despachador como los del agente.
- **D16 · Archivos recibidos.** La API los sirve **por streaming** a la BFF, que
  los pasa al navegador; ningún enlace firmado de S3 llega al navegador (ni a la
  CSP). Solo mensajes del tenant de la sesión (RLS).
- **D17 · Tiempo real.** Canal Redis `inbox:{tenant_id}`. Publican el worker
  (mensaje entrante guardado, mensaje del agente guardado, escalado), la API
  (estados de entrega del webhook de Meta, acciones de la Bandeja) y el admin.
  `GET /console/lite/inbox/stream` (SSE) se suscribe **solo** al canal del
  tenant de la sesión; la BFF lo pasa como hace con el Playground. Si el SSE
  cae —también cuando la plataforma corta una conexión larga de la BFF—, la
  consola reconecta, sondea cada 15 s mientras tanto y lo dice
  («Reconectando…»). Eventos en
  [contracts/realtime.md](contracts/realtime.md).
- **D18 · Notas que no llegan al agente.** `contact_notes` no se lee desde el
  worker ni desde los servidores MCP: lo fija un barrido que falla si el modelo
  o la tabla aparecen en `apps/worker` o `apps/mcp`.
- **D19 · Resumen del agente** = `customer_summary` del último evento de
  escalado. Sin escalado, no hay sección. No hay llamadas nuevas al modelo.
  *Conversaciones del contacto* = 1 + reaperturas por el contacto + filas
  anteriores de ese contacto (las huérfanas de antes de D11).
- **D19b · Borrar no existe** (constitución §IV): una respuesta guardada se
  archiva (`archived_at`), no se borra.
- **D20 · Avisos del cliente.** `console_notifications` gana `audience`
  (`partner` por defecto | `client`). El partner lista solo `partner`; el
  cliente solo `client` con su `external_client_ref`. Tipos de cliente:
  `inbox.waiting`, `client.balance_low`, `client.balance_out` —los dos de saldo
  se emiten donde hoy nace `client.out_of_quota` y el riesgo de saldo, solo si el
  cliente tiene acceso lite—. Los correos de
  `audience = client` van a las membresías activas de cliente de ese tenant y
  **nunca** a los miembros del partner; los del partner no llegan a clientes
  porque están en otra tabla (D1).
- **D21 · Lo que ve el partner.** Las acciones lite se auditan con el tenant y
  vocabulario sembrado (migración), sin contenido —solo longitudes y nombres de
  etiqueta—. La Auditoría del partner ya lee las filas de sus tenants.

### Varios agentes (iteración 3)

- **D22 · Agentes y números.** Tabla `agents` por tenant. `agent_configs` gana
  `agent_id` y la unicidad pasa de `(tenant_id, version)` a
  `(agent_id, version)`. `channels.agent_id` asigna cada número de rol agente a
  un agente. La migración crea un agente por tenant con configuraciones y le
  asigna todas sus versiones y números de rol agente: nadie cambia de
  comportamiento (R14.8).
- **D23 · El agente sale del número.** Webhook (preludio de recibos) y
  despachador resuelven `channel.agent_id` → versión activa de ese agente. El
  cargador cachea por `(tenant_id, agent_id)` y la promoción invalida por
  agente. Un canal sin agente (solo notificaciones) usa el **agente principal**
  —el activo más antiguo del cliente—, que es también el que toman los crones
  sin canal (cobranza, evaluación continua, alertas) y los endpoints sin
  `agent` (compatibilidad con el Companion).
- **D24 · El gasto por agente.** El colector del turno lleva `agent_id`; el
  consumidor lo escribe en `usage_records` y en los asientos de `usage_ledger`.
  Panel y Consumo agrupan por agente desde el libro.
- **D25 · Configuración con el flujo de hoy.** Consola del partner: lista de
  agentes del cliente, «Nuevo agente» (nombre + plantilla → borrador v1 con
  `stage_from_seed`), renombrar y archivar; Agente, Capacidades, Playground y la
  barra de borrador ganan un selector de agente (`?agent=`); en Canales cada
  número elige su agente. Admin: selector y «Nuevo agente» en la pestaña Agente.
  Contratos en [contracts/agents-api.md](contracts/agents-api.md).
- **D26 · Lo compartido.** Conocimiento, grafo, memoria por contacto, modelo
  elegido, conectores y sus overrides siguen siendo del cliente: los comparten
  sus agentes. La lista blanca de herramientas sí es por agente (ya lo es por
  versión).
- **D27 · Mensajes con su agente.** `messages.agent_id` en los mensajes del
  agente, para que el hilo diga qué agente los escribió aunque el número cambie
  de manos después.

## Project Structure

### Documentation (this feature)

```text
specs/030-consola-lite-del-cliente/
├── spec.md
├── plan.md              # este archivo
├── research.md          # por qué cada decisión, y qué se descartó
├── data-model.md        # tablas, columnas, RLS y migraciones 0147–0153
├── quickstart.md        # cómo se comprueba de punta a punta
├── contracts/
│   ├── lite-api.md      # /console/lite/*
│   ├── admin-api.md     # acceso del cliente en el admin
│   ├── agents-api.md    # agentes y números (consola y admin)
│   └── realtime.md      # canal inbox:{tenant} y SSE
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/0147…0153_*.py
├── src/nexus_api/
│   ├── core/client_auth.py                       # ClientPrincipal + require_client_principal (D2)
│   ├── db/models/client_access.py                # ClientAccess, ClientMembership, ClientInvitation
│   ├── db/models/inbox.py                        # ConversationEvent, InboxRead, ConversationTag, ContactNote, SavedReply
│   ├── db/models/agent.py                        # + Agent; AgentConfig.agent_id
│   ├── services/console_identity.py              # load_principal_view con cliente (D4)
│   ├── services/client_access.py                 # activar, módulos, invitar, revocar (D6, D7)
│   ├── services/lite_home.py · lite_usage.py     # Panel y Consumo de un cliente (D8–D10)
│   ├── services/inbox_lifecycle.py               # mark_waiting, resolve, reopen (D11–D13)
│   ├── services/conversation_control.py          # takeover/release extraído del admin (D14)
│   ├── services/inbox_stream.py                  # publicar/suscribir inbox:{tenant} (D17)
│   ├── services/agents.py                        # agentes y números (D22–D25)
│   ├── api/console/auth.py · schemas_auth.py     # PrincipalOut.kind…
│   ├── api/console/lite/{__init__,me,home,usage,notifications,inbox,inbox_media,inbox_stream}.py
│   ├── api/console/agents_list.py · channels.py  # agentes del cliente, número → agente
│   ├── api/admin/client_access.py · agents.py
│   └── metering/wallet.py                        # gasto por agente
├── tests/isolation/test_lite_*.py · test_agent_scope_within_tenant.py · test_contact_notes_never_reach_agent.py
└── tests/unit · tests/integration                # por endpoint y servicio
apps/worker/src/nexus_worker/
├── persistence/messages.py                       # alta de conversación (D11), last_message_at, agent_id
├── runtime/dispatcher.py · agent_loader.py · promote_subscriber.py   # agente por número (D23)
├── metering/collector.py · consumer.py           # agent_id (D24)
└── streams/*                                     # publicar en inbox:{tenant} (D17)
apps/mcp/src/nexus_mcp/servers/escalate/tools.py  # → mark_waiting (D13)
apps/console/src/
├── lib/principal-access.ts · principal.ts · jwt.ts · permissions.ts   # kind cliente, guardas
├── lib/backend/lite.ts                           # liteApi(call)
├── components/shell/{nav.ts,app-sidebar.tsx,…}   # navegación por tipo de persona
├── components/lite/*                             # bloques del Panel y Consumo lite
├── components/inbox/*                            # lista, hilo, cuadro, panel de contacto, respuestas
├── app/(console)/page.tsx · usage/page.tsx       # ramas partner/cliente
├── app/(console)/inbox/page.tsx                  # nueva
├── app/api/lite/inbox/{stream,media/[id]}/route.ts
├── i18n/lanes/{lite,inbox}.ts
└── e2e/lite.spec.ts                              # a11y y recorrido como cliente
apps/admin/src/app/(dashboard)/tenants/[id]/access/*          # pestaña Acceso
apps/admin/src/app/(dashboard)/tenants/[id]/agent/*           # selector y nuevo agente
docs/console.md · docs/consola-lite.md                         # spec viva, en el mismo commit
```

**Structure Decision**: el monorepo existente. Nada de apps nuevas: la consola
lite es la misma `apps/console` con ramas por tipo de persona.

## Complexity Tracking

| Añadido | Por qué hace falta | Alternativa más simple descartada porque |
|---|---|---|
| Dos tablas de membresía de cliente en vez de un rol | Aislamiento por construcción (D1) | Un rol `client` en `partner_memberships` obliga a excluirlo en cada sitio que hoy recorre miembros del partner; el olvidado filtra |
| Cambiar el alta de conversación del worker (D11) | La spec exige que el escalado no parta el hilo (R11.3) y que «resuelta» se reabra (R12.2) | Dejarlo como está mantiene huérfanas las conversaciones escaladas, justo las que la Bandeja tiene que enseñar |
| Extraer la toma de control del admin a un servicio (D14) | Dos llamantes con la misma regla de concurrencia | Copiarla deja dos versiones del `If-Match` que divergen |
