# Investigación (Fase 0): spec 056

Leída contra `develop` en `732576e7` el 2026-11-07, con cuatro barridos de solo lectura y los registros de staging (perfil `nexus`). Cada apartado: **Decisión**, **Por qué**, **Alternativas**, y los anclajes que necesita quien implemente. Las rutas son relativas a la raíz del repo.

---

## R1 · El freno de citas (Requisito 1, D1)

**Decisión.** Un módulo nuevo `apps/worker/src/nexus_worker/runtime/booking_brake.py`, con funciones puras y una sola llamada al modelo de clasificación. Se ejecuta **dentro del handler**, justo después de que el bucle ReAct produce el texto (`pipeline.py:2153`), y no como nodo del grafo.

**Por qué ahí.**
- Solo dentro del handler el reintento puede volver a usar herramientas y conserva los sobres del turno (`envelopes`, `pipeline.py:1773`).
- Una arista de vuelta al handler relee el agente, pierde los sobres y repite herramientas (docstring en `pipeline.py:2496`).
- El revisor de resultados que ya existe (`make_grade_outcome_node`, `pipeline.py:2479`, rúbrica `guardrails/rubrics/restaurant/booking_confirm.md`) no sirve:
  - es opcional (`runtime_outcome_grader`, apagado por defecto);
  - muestrea;
  - reescribe sin herramientas;
  - `_envelope_for_grader` (`outcome_grader.py:238`) descarta `booking` y `refused`, así que da por buena una reserva rechazada.

**Cuándo se salta.** Si ya hay `turn_failure`, si hay `reception_handoff` o si no hay texto. Comprueba el texto y también el `body` y los botones de `interactive_payload`.

**Si el revisor reescribe** (`pipeline.py:2617`), el borrador nuevo se vuelve a comprobar. Si afirma una cita sin respaldo, sale `GRADER_FALLBACK_RESPONSE`.

**Detección, en tres pasos:**
1. Un filtro regex sin tildes, en es, en y pt:
   - confirmad, reservad, agendad, apuntad, cambiad, reprogramad;
   - «tu cita», «te esperamos»;
   - booked, confirmed, scheduled;
   - marcad, «seu horário».
   Sin acierto, la respuesta sale sin llamada.
2. Si hay respaldo, sale sin cambios y sin llamada (escenario 3 de la Historia 1).
3. Solo con acierto y sin respaldo, una llamada `llm.classify(...)` (firma en `llm.py:1779-1810`, patrón de llamada en `pipeline.py:1289-1298`, opciones `CLASSIFY_ON_ANTHROPIC` de 32 tokens) con la pregunta «¿Afirma o implica que hay una cita hecha, confirmada, cambiada o mantenida? YES/NO». El borrador va como mensaje `user`, es decir, como dato (§III).

**Si la llamada falla o vuelve vacía**, cuenta como afirmación: falla cerrado. *Decisión de esta spec.*

**Respaldo.** Se calcula por herramienta. La lista de nombres sale de `TOOL_ACTIONS`/`actions_of` (`apps/api/src/nexus_api/api/console/capability_names.py:969-1015`), donde se añaden `GOOGLECALENDAR_QUICK_ADD` y `GOOGLECALENDAR_UPDATE_EVENT`.

| Herramienta | Respalda cuando |
|---|---|
| `reservas.create`, `reservas.reschedule` | `result.booking` presente y sin `refused`. **Devuelven `status: ok` también al rechazar** (`apps/mcp/.../reservas/tools.py:415-420`, `schemas.py:109,139`) |
| `reservas.answer_offer` | `result.result == "booked"` |
| `booking.create_appointment`, `booking.modify_appointment` (legados) | `status == ok` (un fallo lanza `ToolError`) |
| Composio `GOOGLECALENDAR_CREATE_EVENT`, `_QUICK_ADD`, `_UPDATE_EVENT`, `CALENDLY_POST_INVITEE` | `status == ok` (el proxy marca `error` según `result.error`, `composio_proxy/proxy.py:181-190`) |
| Cita «mantenida»: `reservas.list_mine` con reservas, `reservas.confirm_attendance` | `status == ok` |
| `skipped:dry_run` (Playground), sobres `replayed` | sí |
| `error`, `skipped:*`, `approval_*` (`pipeline.py:2249`), `CALENDLY_CREATE_SINGLE_USE_SCHEDULING_LINK` | **no**. Con ese enlace reserva el cliente. *Decisión de esta spec* |

- Turno en curso: los `envelopes`.
- Turnos anteriores: solo cuando el filtro acierta, una lectura en base filtrada por **esa** conversación (garantía 8):
  - los `messages.tool_calls` salientes desde `attended_at`, sin el límite de 20 de `_load_recent_history`;
  - las filas de `reservations` con ese `conversation_id` y estado en `LIVE_STATUSES` (`reservation.py:50`).

**Reintento.**
- El bucle `pipeline.py:1921-2151` se envuelve en dos intentos.
- El segundo recibe:
  - el borrador como `assistant`;
  - la nota `system` `BOOKING_BRAKE_NOTE` («no se envió: no hay reserva; resérvala con tu herramienta o di la verdad»);
  - `MAX_TOOL_ITERATIONS` de nuevo.
- `tool_once` (`turn_effects.py:101`) evita duplicar una reserva.
- En turnos enrutados sigue dentro de `turn_budget(route.budget)`. Si se agota, va al `turn_limit` de hoy.

**Paso a una persona** (si el segundo intento también afirma):
- El texto pasa a ser `_handoff_line(state)` (`pipeline.py:805`), sin `interactive_payload`.
- `turn_failure = {"kind": "handoff", "reason": "booking_unbacked", "detail": None}`.
- En el despachador:
  - `_ROUTER_REASONS` (`dispatcher.py:481`) acepta `booking_unbacked`; si no, cae a `provider_failure` en `:1355`;
  - sigue por `_apply_gate(fresh=False)` (`:1356`) hasta `inbox_lifecycle.mark_waiting_reason` (`:199`).
- El motivo entra en `WAITING_REASONS` (`apps/api/src/nexus_api/db/models/conversation.py:67`) y en el CHECK (migración 0223).
- **No** va en `GATE_REASONS`, así que la siguiente respuesta del agente no lo libera.
- Con Bandeja, el agente se pausa en esa conversación, como `reception.py:229-232`.
- Sin Bandeja, `tell_escalation_recipients` → `operator_alerts`, como hoy.

**Constancia, sin texto:**
- Una fila de auditoría `agent.booking_brake`, objetivo `conversation:{id}`, `after = {agent_id, turn_id, outcome: retried|handed_off}`. Se escribe en una sesión propia y de mejor esfuerzo, como `_record_router_anomaly` (`dispatcher.py:857`).
- Un evento de log `booking.brake` con `conversation_id`, `turn_id` y `outcome`. **No** llamarlo `result` (lo prohíbe `test_49`).
- Se declaran en `specs/047-la-fabrica-de-agentes/contracts/events.md` §2, §4 y §5.

**Medidor.** El rol `classify` → tarea `classify` (`llm.py:381`) → `record_llm_usage` (`llm.py:1640`), dentro del `usage_turn` que abre `dispatcher.py:1303`. No hay rol nuevo.

**Alternativas.** Encender el revisor de resultados para todos (caro, muestreado, sin herramientas). Solo una regla de prompt (ya existe y falló). Bloquear sin reintento (escala de más).

**Prueba de punta a punta (1.7).** `apps/api/tests/release/test_booking_brake_staging.py`, marcada `manual_only` y con las fixtures de `release/conftest.py`:
- Envía un webhook de Meta firmado a staging (`docs/qa-canales-meta-2026-10-30/07-webhooks-a-staging.md`).
- Usa un agente con Reservas sin horario, así que `reservas.create` sale `refused: hours_missing` de forma determinista.
- Comprueba que el saliente no es una confirmación.

Hoy no existe ninguna prueba de punta a punta del camino de conversación.

---

## R2 · Agentes y Negocio fuera del cliente (Requisito 2, D2)

**Decisión: módulos retirados, no borrados.**
- `CLIENT_MODULES` pasa a `("panel", "inbox", "reservas", "usage")`, y se añade `RETIRED_CLIENT_MODULES = ("agents", "business")` (`apps/api/src/nexus_api/db/models/client_access.py:36-56`).
- Se borran `CONSOLE_V2_MODULES` y los dos `also=` (`core/client_auth.py:197-202`, `services/console_identity.py:333-338`).
- `ordered_modules()` (`:98-102`) ya recorre `CLIENT_MODULES`, así que lo guardado deja de verse antes incluso de la migración.
- `require_client_principal` (`core/client_auth.py:336-346`) acepta los nombres retirados, para que `lite_scope("agents")` siga importando, y siempre responde el 403 de un módulo que no se tiene (`_forbidden`, `:109`). Eso cumple 2.5.
- `set_access` los rechaza con `unknown_module` desde el panel y desde el partner (`services/client_access.py:262`; el panel ya los excluye en `api/admin/client_access.py:120-127`).
- Los avisos:
  - `LITE_LINKS` (`api/console/notifications.py:150-156`) pierde `agent.*` y `channel.*`;
  - el push `agents.state` sigue saliendo (2.7, `push_fanout.py:175-179`) pero enlaza a `auphere-customers://home` (`push_payloads.py:97-100`, `push_fanout.py:373`).
- **Migración 0224**: data cleanup y CHECK con cuatro módulos (ver `data-model.md`).

**Por qué no se borran las rutas.** Borradas, responderían 404 y no el 403 de un módulo ausente. Además obligaría a regenerar el contrato de la app. Borrarlas queda para una limpieza posterior.

**Consola.** `lite-nav.ts:16-23`, `principal-access.ts:26,172-179,193-201` y `components/shell/lite-notifications-bell.tsx:56` pierden los dos módulos. El layout ya manda al primer módulo cualquier ruta cuyo `clientModuleOfPath` sea `null` (`app/(console)/layout.tsx:45-50`), lo que cumple 2.4. Se borran:
- las páginas `app/(console)/agentes/*` y `negocio/*`;
- `components/lite/lite-agents.tsx` y `lite-business.tsx`;
- la lane `i18n/lanes/lite-agents.ts`. Ojo: `lite-agents.ts:133` también tiene los textos de «Corregir esta respuesta». Esos se mueven a su lane antes de borrar (R9).

**Panel.** `tenants/[id]/access/access-form.tsx:31,64-68` deja de conservar los dos módulos. `messages.ts:38-39` y `lib/backend.ts:36`.

**App.**
- Las pestañas ya solo conocen panel, inbox, reservas y usage (`apps/mobile/src/lib/modules.ts:11-17`).
- Inicio (`app/(app)/inicio/index.tsx:30-31,57-60,70-72`) y Ajustes (`app/ajustes.tsx:183-191`) filtran por módulo. La versión publicada los esconde sola.
- Para la siguiente versión:
  - `+native-intent.tsx:19` manda `agents` a `"/"`;
  - se borran `app/agente`, `app/negocio`, `features/agents` y `features/business`;
  - se quitan las invalidaciones de `keys.business` en `conversacion/[id]/corregir.tsx:110-133`.

**Pruebas que fijan lo de hoy y cambian.**
- API:
  - `unit/test_console_identity_client.py:92`
  - `unit/test_lite_me_nav.py:36-39`
  - `integration/lite/test_lite_agents_business.py:54,715`: 16 pruebas que pasan a afirmar 403
  - `isolation/test_lite_client_vs_client.py:70,300-306`
  - `integration/test_dev_seed_fabrica.py:204,244`, con su seed `scripts/dev_seed_fabrica.py:90`
- Consola: `lite-nav.test.ts`, `lite-bell-links.test.ts`, `lite-{agents,business}.test.tsx` (se borran), `app/__tests__/page-guards.test.ts:61` y `inbox/__tests__/design-045.test.tsx`.
- Panel: `access-form.test.tsx:68-69`.
- App: `__tests__/{agentes,negocio,inicio,push,fabrica-avisos}.test.tsx`.
- `no-orphan-keys.test.ts` obliga a borrar las claves huérfanas.

---

## R3 · Acceso desde la consola de partners (Requisitos 3 y 4, D3, D4)

**Decisión.** Un router nuevo `apps/api/src/nexus_api/api/console/client_access.py`, montado como `client_bags` (`api/console/__init__.py:168`), que llama a los **mismos** servicios que el panel (`services/client_access.py`). El servicio solo recibe `actor: str`: el partner pasa `principal.actor` (`console:<email>`, `core/console_auth.py:178-201`) y el panel `operator:<email>`.

| Ruta del partner | Servicio |
|---|---|
| `GET /console/clients/{ref}/client-access` | `read_access(session, tenant_id)` (`:183`) |
| `PUT /console/clients/{ref}/client-access` | `set_access(..., enabled, modules, actor, reservas)` (`:245`): modo, `on_live`, `inbox_requires_whatsapp`, `no_modules`, cierre de sesiones, liberación de escalados |
| `POST /console/clients/{ref}/client-members` | `invite(..., email, name, actor)` (`:350`) y `_send` tras confirmar, como el panel (`api/admin/client_access.py:233`) |
| `POST /console/clients/{ref}/client-members/{member_id}/resend` | `resend` (`:411`) |
| `POST /console/clients/{ref}/client-members/{member_id}/revoke` | `revoke` (`:443`) |

**Sesión de base.**
- `ref` → tenant con `resolve_mapping` (`api/console/deps.py:80-87`, 404 opaco).
- **No** se usa `client_scope` (`:90`), que baja a `nexus_app`: `invite` y `_end_sessions` tocan `console_auth.*`, que no tiene grant para ese rol (`alembic/versions/0118_signup_and_identities.py:36-38`).
- Se hace como el panel: `async with session.begin(): await declare_tenant(session, mapping.tenant_id)`.
- Además, si `read_access(...).partner.id != principal.partner.id`, `unknown_client()`.

**Esquemas.** Los de `api/admin/client_access.py:52-162` pasan a un módulo compartido. La salida del partner va **sin** `partner{id}`.

**Permiso.** `client_access:manage = ["owner", "admin"]`:
- en la API: `PERMISSIONS`, `core/console_auth.py:97-150`;
- en la consola: `apps/console/src/lib/permissions.ts`;
- la prueba de deriva: `API_MAP` de `apps/console/src/lib/__tests__/permissions.test.ts:10-41`;
- una fila en `components/team/roles-table.tsx:17`.

**Auditoría.** Las frases existen (`0148_client_audience_vocab.py:30-66`), pero dicen «Auphere cambió…» a fuego. La migración 0225 las reescribe con `{actor}`. `_human_actor` ya enseña el correo de `console:` y «Auphere» para `operator:` (`api/console/audit.py:190-215`). Vigilar `tests/unit/test_console_audit_words.py`.

**Invitar.**
- `invite` ya exige el acceso encendido (409 `access_disabled`) y **rechaza correos con cuenta de partner o de otro cliente**. Eso acota el riesgo aceptado en D3: el partner tendría que usar otro correo.
- Token de un solo uso, solo hash, 21 días. Correo por Resend con `send_client_invitation`.
- **No hay límite de frecuencia** en ningún camino, y Resend se comparte (100 al día).
- Se añade `core.rate_limit.allow(redis, key=f"console:client_invite:{partner_id}", per_minute=settings.console_client_invites_per_minute, surface="console")` → 429, como `api/console/support.py:160-168`. Ver Complexity Tracking.

**Barrido de aislamiento.** `tests/isolation/test_console_scope.py` se calcula de `app.routes`, así que las rutas nuevas entran solas en:
- `:281`: sin identificadores en la ruta o el cuerpo;
- `:301`: sin cuerpos ni ids internos;
- `:384`: todas exigen principal;
- `:490`: el 404 opaco con un `ref` de otro partner. Hay que añadir PUT `{"enabled": false, "modules": []}` y POST `{"email": "x@example.com"}` a `_minimal_body` (`:430-486`);
- `:620`: sin palabras ni teléfono del cliente final.

Y `test_lite_route_scope.py:70`: una persona de cliente no llega a rutas del partner.

**Consola (pestaña).**
- `components/shell/routes-v2.ts:7` añade `ClientTab "access"`. También `client-header-v2.tsx:18-27` (`TABS`, `activeTab`) y `crumbs-v2.ts`.
- La cabecera es un componente de cliente: el layout le pasa `canManageAccess={can(principal.role, "client_access:manage")}` (`clients/[ref]/layout.tsx:48`).
- La página `app/(console)/clients/[ref]/access/page.tsx` copia `business/page.tsx:35-68`, con `notFound()` sin permiso (3.2 también por la dirección).
- Acciones `access/actions.ts` como `business/actions.ts:38-60`, pero con `backendFor(principal)`: el arnés `src/test/actions.ts:115-118` solo simula `backendFor`.
- La lógica de la tarjeta se porta de `access-form.tsx` del panel, que vive en otro workspace de pnpm y no se comparte.
- Filas: patrón `connector-model.rowLayout` + `agent-connectors.tsx:555-650`, con `DropdownMenuItem variant="destructive"` al final y `ConfirmDialog returnFocus`.
- Textos: lane nueva `i18n/lanes/client-access.ts`, registrada en `i18n/messages.ts`. `clients.v2.tab.access` va en `lanes/business.ts:305-307`. **Sin punto y coma** (`words.test.ts:70`).

**Alternativas.** Reutilizar el componente del panel (otro workspace: no). Un permiso existente como `clients:write` (daría la pestaña al builder: D4 lo descarta).

---

## R5 · Un juego de reglas para horario y servicios (Requisito 5, D5)

**Por qué hoy no coinciden.**
- Reservas pide duraciones múltiplo de 15 por la spec 043 (`data-model.md:88`).
- La 0183 amplió la base a 5–480 en pasos de 5 (`db/models/reservation.py:173-177`, `services_catalog.py:54`). El motor no necesita el 15: `services_slots` (`services/reservations/engine.py:198-218`) solo exige `cursor + duration <= end`.

**Decisión: las reglas compartidas.**

| Dato | Regla |
|---|---|
| Turnos por día | 0 a 6 (`MAX_SHIFTS_PER_DAY`, `db/models/business.py:320`) |
| Minutos | paso de 5. 24:00 vale como cierre |
| Nocturnos | permitidos, sin solapes, tampoco con el día siguiente (`hours.py:183-190`) |
| Sede | Reservas edita solo la semana del negocio. El horario propio de una sede se enseña sin poder editarse (`reservations/core.py:126` no conoce sedes) |
| Duración | de 5 a 480, en pasos de 5 |
| Precio | `none`, `free` o `amount` (`PRICE_KINDS`, `reservation.py:45`). «Gratis» = `price_kind='free'` con `price_minor NULL` (CHECK `:182-185`) |
| Importe | entero en unidades menores, de 0 a **10¹²** (`schemas_business_sections.py:213`). Con 10⁹, 10 M COP serían el tope |
| Categoría | 40 como máximo (columna `String(40)`, `CATEGORY_MAX` en `services_catalog.py:52`). Se corrige el `max_length=80` de `reservas_schemas.py:168,180` y de `schemas_business_sections.py` |
| Nombre | 1 a 120. El cliente no renombra (D5) |

**Dónde vive.**
- Python: `apps/api/src/nexus_api/services/business/rules.py`, con las constantes (reexporta las de los modelos) y los chequeos de paso y tope. Lo importan los dos esquemas.
- Reservas crea y edita servicios por `services_catalog.create_service`/`update_service`, en lugar de escribir la tabla (`reservas.py:583-637`). Así hay un solo validador y queda el historial.
- TypeScript: `apps/console/src/lib/business-rules.ts`, importado por:
  - `business/sections/hours-model.ts` y `services-model.ts`;
  - `reservas/model/hours.ts` y `services-settings.tsx`;
  - los zod de `app/(console)/reservas/actions.ts`.

**Escribir solo lo tocado (5.3).**
- **Horario.**
  - Lectura: `SettingsOut.hours` con la forma de la ficha (`hours_view`, `api/console/business.py:311`).
  - Escritura: `PATCH /console/lite/reservas/business-hours {days: {mon: [...]}, revision}`. El servidor carga la semana, sustituye solo esos días, mantiene «blocks» si lunes a viernes siguen iguales (si no, pasa a «daily») y llama a `save_week(expected_revision=…)`.
  - En la consola: `changedDays(original, draft)`. El editor es el de la ficha (`shift-editor.tsx` + `hours-model.ts`), sacado a un componente puro.
  - Hoy se pierde: un PUT de la semana entera (`hours-editor.tsx:121`, `reservas.py:251-272`) que lee la proyección antigua (`hours.py:531-552`, parte los nocturnos y convierte 24:00 en 23:59) y rechaza más de 2 tramos.
- **Servicios.**
  - `ServiceOut` lleva `price: {kind, amount_minor?}`, como el `PriceOut` de la ficha.
  - El PATCH acepta `price: PriceIn` en lugar de `price_minor`/`clear_price`.
  - La consola envía solo lo que cambió. `update_service` conserva lo que no llega (`services_catalog.py:568-571`).
  - Hoy, `price_minor: null` lo convierte en `none` (`reservas.py:625-628`).

**Renombrar (5.4).** Si el nombre es distinto del guardado, `ServicePatchIn.name` (`reservas_schemas.py:172`, aplicado en `reservas.py:615`) devuelve `422 {code: "rename_not_allowed", field: "name"}`. `ServiceIn` conserva `name` para crear. En la consola, el nombre se ve sin poder editarse al editar, como `renameable={false}` en la ficha (`services-section.tsx:263,367-370`).

**«Revísalo» (5.5).** Se calcula al leer, sin columna: turnos con minutos que no son múltiplo de 5 (la API aceptaba cualquiera, `hours.py:89-100`). Duración y categoría no pueden incumplir.

**Errores (5.6).**
- Hoy el `.parse` de zod lanza y el cliente enseña `common.error.backend` (`services-settings.tsx:226,409`).
- Cambia a `safeParse` → `{status: 422, code, field}`, con los códigos traducidos en `business.services.error.*`.
- Un 422 deja de quedarse en `reservas.error.invalid` (`vocab.ts:122`).

---

## R6 a R16 · Bandeja, errores, validación y formatos

**Requisito 6.**
- El valor `all` no cambia, ni en la URL ni en la API ni en el tipo. Solo cambia el texto de `inbox.filter.all`: «Abiertas» / «Open».
- `ListPage` y `ConversationPageOut` ganan `resolved: int`, que se calcula solo con `flt == "all"` y la página vacía (`inbox_view.py:312-319,449`; `lite/inbox.py:128-133,494`).
- Consola:
  - estado vacío en `conversation-list.tsx:171-187`;
  - botón `onFilter("resolved")`;
  - texto `inbox.empty.clear`.
- App: `apps/mobile/src/app/(app)/bandeja/index.tsx:116` tras `pnpm gen`. Puede salir por OTA (`expo-updates`).
- `has_any` se queda, porque lo leen apps viejas.

**Requisito 7.**
- `REASONS` y `reasonKey` (`builder/improve-model.ts:54-76`, `i18n/lanes/agent-improve.ts:43-58`) pasan a `apps/console/src/lib/waiting-reasons.ts`.
- Se añade `inboxReasonText(raw, t)`:
  - un código conocido da el texto de la tabla;
  - un código desconocido o `escalated` da «El agente pidió ayuda»;
  - el texto libre del agente (`escalate/tools.py:69`, hasta 500 caracteres) sale tal cual. *Decisión de esta spec.*
- Se usa en `event-text.ts:26`, `thread.tsx:112`, `composer.tsx:74` y `conversation-row.tsx:105`, con el código de la columna primero (`waiting_reason`/`waiting_code`, `lite/inbox.py:371,455-460`).
- Faltan en la tabla `out_of_audience` y `booking_unbacked`.
- La app tiene su lista (`mobile/src/features/inbox/model.ts:180-193`) y pinta el texto crudo en `conversation-row.tsx:39`: se arregla igual.

**Requisito 8.**
- Transiciones que acaban la espera:
  - `take_over` (`lite/inbox.py:639-677`);
  - `give_back` (`:679-712`);
  - `inbox_lifecycle.resolve` (`:327-344`), que cubre también archivar;
  - `release_reason` (`:255-273`, desde `dispatcher.py:929`);
  - `release_escalated_for_tenant` (`:385-417`, desde `client_access.py:304`).
- **Decisión: migración 0227** con `console_notifications.handled_at`, y no reutilizar `read_at`, que mezclaría leído con atendido.
- `mark_waiting_handled(...)` se llama tras el commit:
  - en las rutas lite, `scope.after_commit` (`lite/deps.py:74-93`);
  - en el worker y en `client_access`, con la búsqueda de `_notify_waiting` (`inbox_lifecycle.py:290-322`).
- `_read_expr` y `_unread_count` (`api/console/notifications.py:79-90,203-209`) tratan lo atendido como no pendiente.
- La app ya cuenta del estado vivo (`push_fanout.py:283-296`).

**Requisito 9.**
- Con alcance `business`, una corrección hermana por cada agente `published` o `paused` (precedente en `api/console/channel_config.py:325`), sin condicionar por papel ([[agentes-sin-papel-fijo]]).
- Cada una con su propuesta, unidas por `batch_id`: migración 0226 con FK compuesta, ver [[fk-no-pasa-por-rls]].
- El agente en el que la propuesta no valida se salta y queda en `after_json` de `correction.proposed`.
- Un solo aviso por lote.
- Ruta nueva `POST /console/clients/{ref}/corrections/{batch_id}/accept|discard`, en una transacción (`_apply_change` recibe `agent_id`).
- `ImprovementOut` gana `batch {id, agents_count}`.
- Anclajes: `corrections.py:283,354-425`, `inbox_correction.py:116`, `agent_improvement.py:47,283,310,336,380`.

**Requisito 10.**
- Límites de error que alcanza un cliente:
  - `(console)/error.tsx`;
  - `inbox`, `reservas`, `negocio` y `agentes/error.tsx`;
  - un fallo del layout (`(console)/layout.tsx:36`), que no tiene `app/error.tsx` y por eso sale la página de Next en inglés.
- Decisión:
  - un `ViewerKindProvider` montado en `ConsoleShellV1` con `who.kind`;
  - `RouteError` (`components/error-boundary.tsx:17-33`) no pinta `error.message` con un cliente, ni con nadie si hay `digest`;
  - se añade `app/error.tsx`.
- **Registros de staging (00:00–06:00 UTC del 2026-11-07)**:
  - cero respuestas que no sean 2xx en sesión, lite y Reservas;
  - 38 cargas de Reservas, todas en 200;
  - recargas completas a las 01:54:27, 01:54:35, 01:54:46, 01:55:26 y 01:55:36, que encajan con QA reintentando.
- Los registros de Vercel de ese día **ya no existen** (más de una hora: 400). La causa nació en la consola.
- Las candidatas:
  - `session()` relanza todo lo que no sea 401 (`lib/backend.ts:818`), y `request()` (`:99-126`) no tiene reintento ni tiempo límite;
  - algo que lanza al pintar.
- Decisión:
  - `apps/console/src/instrumentation.ts` con `onRequestError`, que registra el digest, la ruta, `routeType` y `cause.code` en JSON;
  - un reintento y un tiempo límite en `session()`;
  - un Playwright de diez repeticiones contra staging (`quickstart.md`).
- Si la causa aparece en ese registro, se corrige en la misma rama.

**Requisito 11.**
- **Lista de espera**: `onBlur` + `disabled={!ready}`, como `booking-dialog.tsx:151,156,265`, en `add-waitlist-dialog.tsx:96-126,178`.
- **Correo**: `EmailStr` (ya es dependencia: `email-validator>=2.2.0`, `apps/api/pyproject.toml:34`) en `reservas_schemas.py:128,134`, con máximo 254. La consola pasa de 200 a 254.
- **Fecha especial**: se rechaza con `date_past` en `special_dates.py:106,152` si `to < hoy` en la zona del negocio. No va en `SpecialDay.__post_init__`, para que deshacer y cargar sigan funcionando. Consola: `special-dates-section.tsx:166-180`.
- **Navegador**: `noValidate` en `business-sources.tsx:209`, `services-section.tsx:507` e `inbox/saved-replies.tsx:158`, y en todo formulario nuevo.

**Requisito 12.**
- `ConfirmDialog` de `@nexus/ui` en `services-section.tsx:152,168,239`, `locations-section.tsx:126` y `special-dates-section.tsx:112`.
- Deshacer: la confirmación va en `SectionHistory` (`business/history/section-history.tsx:143`).
- `useDiscardGuard(dirty, onClose)` nuevo, en `src/components/use-discard-guard.tsx`, para los 9 diálogos de Reservas:
  - `cancel-dialog.tsx:87`
  - `add-waitlist-dialog.tsx:81`
  - `hours-editor.tsx:142`
  - `services-settings.tsx:234,417`
  - `capacity-booking-dialog.tsx:127`
  - `block-dialog.tsx:73`
  - `walkin.tsx:167`
  - `booking-dialog.tsx:131`

**Requisito 13.**
- `apps/console/src/lib/amount.ts`: `formatAmount` (Intl con el idioma de la persona), `parseAmount` (coma o punto, con tope) y `amountInput`.
- `lib/money.ts:formatMoney` delega en él.
- Llamadas a cambiar:
  - `booking-detail.tsx:113`
  - `services-settings.tsx:315,370,376,456`
  - `services-section.tsx:36,126,322,337`
  - `lite-spend-card.tsx:14,92`
  - `services-model.ts:14-70`
- Intl en español no agrupa cuatro cifras («1500,00 €»): es el formato del idioma.
- Teléfono: `display_handle(identifier, channel)` en `services/inbox_view.py:409-410,695-696` pone «+» en WhatsApp. Agrupar haría falta libphonenumber: queda fuera.

**Requisito 14.**
- `getT()` sin argumento en `(auth)/layout.tsx:6`.
- `auth-pages-locale.test.ts:42-47` pasa a revisar todos los `.tsx` de `(auth)`. Hoy sale en rojo.
- 404:
  - `(console)/not-found.tsx` con menú y enlace a `firstModulePath`/`firstPartnerModulePath`;
  - el raíz, asíncrono, con `resolvePrincipal()`: con sesión dentro de un `ConsoleFrame` sacado de `(console)/layout.tsx:36-73`, sin sesión con «Entrar».
- **No** se añade un catch-all `[...rest]`: el layout ya manda al cliente a su primer módulo.

**Requisito 15.**
- `resolve_session` (`console_identity.py:465-490`) devuelve `expires_at`, y `SessionOut.expires_at` (`schemas_auth.py:95`) se añade sin renovar nada.
- En la consola: `PrincipalBase.sessionExpiresAt` (`principal-access.ts:118-146`).
- `<SessionExpiryNotice>` en el layout raíz:
  - un toast que no bloquea, con «Volver a entrar»;
  - una sola vez por `expiresAt`, en localStorage dentro de try/catch.

**Requisito 16.**
- Lo cubren `resolve.test.tsx:46-103` y `test_lite_inbox_clear_archive.py:49-130,192-215`.
- Faltan dos pruebas:
  - Eliminar → el contacto escribe → conversación nueva, pasando por `worker/persistence/messages.py:144` y `dispatcher._mark_attended` (`:762`);
  - el actor de la auditoría es `client:<email>` (`client_auth.py:100-103`).

---

## Coordinación con otras ramas

- **`reservas-fuente-unica-631d6d`** (99 archivos sin commit) trae la regla del calendario compartido (043 R12.4).
  - Su migración se pensó como `0222_staff_calendar_connections`, y `0222` es hoy la de unión (`732576e7`), así que tendrá que renumerarse otra vez.
  - Lo que se fusione después de esta rama numera desde `0227`.
  - El guion `.claude/commits/2026-11-05-calendario.sh` ya no sirve tal cual.
- **La app** necesita versión nueva solo para los enlaces directos y para limpiar pantallas. Todo lo demás llega por la API o por OTA.
