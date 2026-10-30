# Contrato — API de la consola de partners (`/console/*`)

Superficie `0`. Todas las rutas:
- pasan por la puerta de hoy: token EdDSA de 60 s que la API vuelve a verificar
  contra `partner_memberships`;
- entran en `tests/isolation/test_console_scope.py`;
- devuelven `allowed` (las acciones que la persona puede hacer) en cada recurso, y
  la consola no pinta lo que no está permitido (§V).

Ninguna respuesta lleva cuerpos de mensaje, teléfonos de clientes finales ni
costes (C1, C8 y C9): el barrido del requisito 56.9 lo comprueba.

## Convenciones

- **Cliente**: `{ref}` (la referencia externa del cliente, como hoy). **Agente**:
  `{agent_id}` (uuid), siempre bajo su cliente.
- **Concurrencia**: los recursos editables devuelven `revision` y `ETag`. Las
  escrituras exigen `If-Match`; si no coincide, responden `412` con `current` y
  `changes` (lo que cambió desde la revisión leída).
- **Idempotencia**: las acciones con efecto (crear, asignar, publicar, pausar,
  conectar) aceptan `Idempotency-Key`. Repetida, la misma respuesta.
- **Trabajos**: lo que tarda (leer la web, construir, probar, publicar,
  certificar) responde `202` con `job_id`. La consola consulta
  `GET /console/jobs/{job_id}` con espera creciente (1, 2, 4… hasta 10 s).
- **Errores**: `{ "error": { "code", "message", "fix" } }`, con `message` en
  español y `fix` (una acción) cuando la hay.
- **Dinero**: `{ "amount_micros": int, "currency": "EUR" | "USD" }`, con
  `amount_micros` en cien milésimas de la moneda. Los precios del negocio van en
  unidades menores de su moneda ISO 4217.
- **Permisos**: entre corchetes, el permiso de `console_auth`.

## 1. Marco

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /console/search?q=` | ⌘K: clientes (con sus pestañas), agentes (con su cliente), pantallas y acciones permitidas | 47.2 |
| `GET /console/notifications?unread=&limit=` | Avisos; `limit=5` para la campana | 47.3, 49.5 |
| `POST /console/notifications/read-all` | Marcar todo como leído | 47.3 |
| `GET /console/home` | Bloques del Panel y «Necesita tu atención», con el arreglo de cada fila | 48 |
| `GET /console/jobs/{job_id}` | Estado de un trabajo: `queued`, `running`, `done`, `failed`; `progress` y `result` | — |

## 2. Clientes

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /console/clients?q=&filter=all\|attention\|active\|archived` | Lista: nicho, estado con motivo, agentes con su `visible_state`, bolsa (`balance`, `days_left`, `pct_left`), `attention` y `allowed` | 7 |
| `GET /console/clients/niche-suggestions?q=` | Nichos de plantillas y los más usados | 4.2 |
| `POST /console/clients/link-detection` | `{info}` → chips `{kind, value, target}` | 5.1, 5.2 |
| `POST /console/clients` [`clients:write`] | `{name, niche, info?, country?, timezone?, price_currency?, wallet_currency?, eu_only?}` → `201 {ref}`. No crea agentes. Si se detectó web o redes, lanza la lectura | 4 |
| `GET /console/clients/{ref}` | Cabecera, ciclo de vida y `allowed` | 6 |
| `PATCH /console/clients/{ref}` [`clients:write`] | Mismo modal que el alta; `If-Match`. La zona horaria se valida como IANA | 6.1–6.3 |
| `POST /console/clients/{ref}/archive` · `/restore` | Pausa sus agentes recordando su estado / los devuelve | 6.4, 6.5 |
| `DELETE /console/clients/{ref}` [`clients:delete`] | Borrado RGPD de hoy: archivado antes y nombre tecleado; `409` legal | 6.6 |
| `GET /console/clients/{ref}/panel` | Panel del cliente: bolsa, días, reparto por agente, actividad del mes, ranking, lo primero que le falta a la ficha y la tarjeta de lectura | 14 |

## 3. Negocio (la ficha)

Todas bajo `/console/clients/{ref}/business`. Cada sección tiene su `revision`.

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /` | ClientSpec + estado de cada sección + procedencia + sugerencias pendientes | 8, 13 |
| `PUT /basics` | Datos básicos | 8 |
| `GET /locations` · `POST /locations` · `PATCH /locations/{id}` · `POST /locations/{id}/archive` · `/restore` | Sedes | 9 |
| `PUT /hours?location_id=` | Horario por bloques o día por día, con hasta 6 turnos; devuelve `label` («Así lo dirá el agente») | 10 |
| `POST /special-dates` · `PATCH /special-dates/{id}` · `POST /special-dates/{id}/archive` | Fechas especiales | 10.3 |
| `GET /services` · `POST /services` · `PATCH /services/{id}` · `POST /services/{id}/archive` · `POST /services/{id}/duplicate` | Servicios | 11 |
| `PUT /services/{id}/agents` | `{"mode": "all_agents" \| "list", "agent_ids": []}` | 11.2, 11.3 |
| `PUT /policies` | Cancelación, pagos, señal y no presentarse | 8.1 |
| `POST /faqs` · `PATCH /faqs/{id}` · `POST /faqs/{id}/archive` | Preguntas frecuentes del negocio | 8.1, 18.3 |
| `PUT /links` | Redes y web | 12.4 |
| `GET /sources` · `POST /sources` (multipart ≤ 10 MB, o `{url}`) · `POST /sources/{id}/reread` · `POST /sources/{id}/remove` · `POST /sources/{id}/restore` | Documentos y webs de la capa del negocio | 12 |
| `POST /read` | Leer la web y las redes en segundo plano → `202 {job_id}` | 5 |
| `POST /suggestions/{id}/decide` | `{decision: accept \| edit \| discard, value?}` sobre un dato leído o sugerido | 5.8, 13.2, 18.2 |
| `GET /history?section=` · `POST /history/{change_id}/undo` | Historial y deshacer | 13.3 |
| `POST /builder` | «Completar con el constructor» → `202 {job_id}`, con propuesta por secciones | 18 |
| `GET /export` · `POST /import?dry_run=` | ClientSpec v1 (`client-spec.schema.json`); importar crea una propuesta | 8.3 |

## 4. Agentes

Todas bajo `/console/clients/{ref}`.

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /agents` | Tarjetas: nombre, `visible_state`, propósito, canales, gasto, la pestaña a la que abre e `is_reception` (lo que dice la versión publicada) | 26.1, 35 |
| `POST /agents/draft-jobs` [`agents:write`] | `{name, description, start: describe \| template \| blank, template_id?}` → `202 {job_id}`. El agente se crea en borrador al primer borrador | 17 |
| `POST /console/jobs/{job_id}/answers` (ruta absoluta) | Respuestas a las preguntas del constructor, con dónde se guarda cada una (ficha o «Solo este agente») | 17.4, 17.5 |
| `PUT /default-agent` | `{agent_id}`; atómico | 26.2 |
| `GET /agents/{agent_id}` | Cabecera, vida, `visible_state`, por defecto, `allowed`, tope y gasto del mes, `is_reception` | 25, 35, 44.1 |
| `PATCH /agents/{agent_id}` | Renombrar; tope mensual `{monthly_cap: Money \| null}` | 26.4, 44.1 |
| `GET /agents/{agent_id}/draft` · `PATCH /agents/{agent_id}/draft` · `DELETE /agents/{agent_id}/draft` | El borrador (AgentSpec + `revision` + vista previa compilada + estado de las pruebas); descartar vuelve a la activa | 3, 16 |
| `POST /agents/{agent_id}/proposals/{id}/apply` · `/reject` | Aplicar o rechazar una propuesta (`state_hash`, caduca en 15 min) | 15.2, 15.3 |
| `POST /agents/{agent_id}/publish` | «Guardar» → `202 {job_id}`: compila, valida, prueba, revisa y decide. `{note, accept_normal_failures?, override_reason?}` (`override_reason` solo para owner y admin) | 23 |
| `POST /agents/{agent_id}/publish/undo` | Deshacer, durante 10 minutos | 24.1 |
| `GET /agents/{agent_id}/versions` · `GET /agents/{agent_id}/versions/{n}` · `POST /agents/{agent_id}/versions/{n}/restore` | Historial y restaurar (crea un borrador) | 24 |
| `GET /agents/{agent_id}/tests` · `POST /agents/{agent_id}/tests` · `PATCH /agents/{agent_id}/tests/{id}` | La suite; «No aplica» con razón | 21 |
| `POST /agents/{agent_id}/test-runs` | `{scope: all \| affected \| one, test_id?}` → `202 {job_id}`. Con una pasada viva del agente, devuelve esa y no encola otra (T217) | 21.4 |
| `GET /agents/{agent_id}/review` | Hallazgos con gravedad y arreglo | 22 |
| `POST /agents/{agent_id}/playground/sessions` · `POST /…/sessions/{id}/messages` · `PATCH /…/sessions/{id}` | Playground sobre el borrador o una versión, con hora y agenda simuladas; devuelve burbujas y «Lo que habría hecho» | 20 |
| `POST /agents/{agent_id}/copilot` | `{message, context?}` → respuesta con citas y propuestas (a un analyst solo le explica) | 19 |
| `POST /agents/{agent_id}/teach` | `{text, scope: business \| agent}`: se aplica al momento, con historial y deshacer | 37.3 |
| `GET /agents/{agent_id}/knowledge` · `POST /agents/{agent_id}/knowledge` | Fuentes de la capa del agente | 37 |
| `GET /agents/{agent_id}/quality` | Opciones con precio estimado, comprobación y precio real de 7 días | 39.4, 39.5 |
| `POST /agents/{agent_id}/quality/check` | `{model_policy}` → `202 {job_id}` (certificación del agente) | 39.9 |
| `POST /agents/{agent_id}/pause` · `/resume` | Pausar o reanudar; dice cuántas conversaciones hay en curso | 27 |
| `POST /agents/{agent_id}/archive` | `{channels: [{channel_id, to_agent_id \| "pause"}]}` | 28 |
| `POST /agents/{agent_id}/restore` | Vuelve en pausa | 28.2 |
| `GET /agents/{agent_id}/performance?days=30` · `GET /agents/{agent_id}/conversations?cursor=` | Rendimiento y lista **solo con metadatos** | 51.1, 51.2 |
| `GET /agents/{agent_id}/improvements` · `POST /…/improvements/{id}/accept` · `/discard` | Sugerencias semanales y correcciones de comportamiento | 51, 52.2 |

## 5. Canales

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /console/clients/{ref}/agents/{agent_id}/channels` | Canales del agente y el enlace pendiente | 29 |
| `POST /…/agents/{agent_id}/channels/whatsapp/signup` | Arranca Embedded Signup v5 para ese agente: devuelve la configuración del SDK | 30 |
| `POST /…/agents/{agent_id}/channels/whatsapp/complete` | `{code, mode, waba_id, phone_number_id, history_import?}`; el número queda asignado al agente y su `config` se combina | 30.1, 30.7, 30.8 |
| `POST /…/agents/{agent_id}/channels/owner-links` | `{mode}` → la URL, **una sola vez**; revoca el pendiente si se confirma | 31.1, 31.2, 31.7 |
| `DELETE /…/owner-links/{id}` | Revocar | 31.7 |
| `GET /console/clients/{ref}/channels/{channel_id}` | Página del canal: audiencia, excepciones, escalado, espera, comprobaciones, `revision` | 32 |
| `PUT /…/channels/{channel_id}/config` | `If-Match`; se aplica desde el siguiente mensaje | 32.7 |
| `POST /…/channels/{channel_id}/config/undo` | Deshacer, durante 10 minutos | 32.7 |
| `GET /…/channels/{channel_id}/history` | Historial con antes y después | 32.7 |
| `POST /…/channels/{channel_id}/move` | `{to_agent_id}` | 34.2 |
| `POST /…/channels/{channel_id}/pause` · `/resume` | | 27 |
| `POST /…/channels/{channel_id}/disconnect` | Pide confirmación; queda pendiente con «Reintentar» si Meta falla | 34.3, 34.4 |

**Forma de `config`:**

```json
{
  "audience": { "mode": "unset | team_only | everyone", "test_numbers": ["+34…"], "exceptions": ["+56…"] },
  "escalation": {
    "recipients": [
      { "name": "Marta", "via": "whatsapp", "phone_e164": "+34…" },
      { "name": "Recepción", "via": "inbox", "client_user_id": null }
    ],
    "summary": true
  },
  "wait_message": "Gracias por escribir. Te respondemos enseguida.",
  "notify_from": "channel | auphere"
}
```

`notify_from` es solo lectura: lo decide si el número tiene la plantilla de
aviso aprobada (requisito 33.3).

## 6. Integraciones

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /console/clients/{ref}/agents/{agent_id}/integrations?q=&category=` | Catálogo permitido al partner, primero lo que piden las habilidades; estado de conexión y de activación | 35.2 |
| `POST /console/clients/{ref}/connections` | `{integration}` → autorización (OAuth u otro formulario) | 35.3 |
| `PUT /…/agents/{agent_id}/activations/{integration}` | `{permission: read \| ask_before_write \| read_write, settings}`; ajustes validados con el esquema del catálogo | 35.1, 35.5, 36.2 |
| `DELETE /…/agents/{agent_id}/activations/{integration}` | Devuelve las habilidades afectadas | 35.7 |
| `GET /console/clients/{ref}/connections/{id}` | Cuenta, salud con la hora de la última comprobación, agentes y permisos, ajustes | 36.1 |
| `POST /…/connections/{id}/reconnect` · `POST /…/connections/{id}/disconnect` | Desconectar para todos lista lo afectado y pide confirmación | 36.4 |

## 7. Dinero

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /console/wallet` | Cuenta: moneda, «Saldo disponible» (sin pool), «En bolsas» (aprox. si hay otra moneda), gasto del mes y proyección | 46.1 |
| `GET /console/wallet/bags` | Bolsa de cada cliente: saldo, gastado del mes, días, relleno | 46.2 |
| `GET /console/wallet/fx?from=&to=` | Cambio BCE del día y su fecha | 45.2 |
| `POST /console/clients/{ref}/bag/assign` [`usage:write`] | `{amount: Money, refill_up_to?: Money \| null, alert_low?: bool}` + `Idempotency-Key` → recibo | 43.4, 45 |
| `POST /console/clients/{ref}/bag/lower` [`usage:write`] | Devuelve a la cuenta lo no gastado | 43.6 |
| `POST /console/wallet/bags/move` [`usage:write`] | `{from_ref, to_ref, amount}`: un solo traspaso | 43.7 |
| `PUT /console/clients/{ref}/bag/refill` · `PUT /console/clients/{ref}/bag/currency` | Relleno mensual; cambio de moneda con conversión confirmada | 43.3, 43.8 |
| `POST /console/clients/{ref}/bag/request` | «Pedir saldo» `{note?}`; `429` con `retry_after` si ya se pidió hoy | 45.7 |
| `GET /console/usage/summary?period=` · `GET /console/usage/daily?days=7\|30\|90&client=&line=` · `GET /console/usage/detail?…` · `GET /console/usage/export.csv?…` | Consumo por partidas, gráfica, detalle técnico y CSV | 46 |
| `GET /console/usage/build-budget` · `POST /console/usage/build-budget/extension-request` | Partida «Construcción y pruebas» y «Pedir ampliación» | 46.5 |
| `GET /console/wallet/migration` · `POST /console/wallet/migration/confirm` | «Repartir tu saldo en bolsas» | 55.3 |

**Recibo de una asignación:**

```json
{
  "client_balance_before": { "amount_micros": 1550000, "currency": "USD" },
  "assigned": { "amount_micros": 2000000, "currency": "USD" },
  "debited_from_account": { "amount_micros": 1843000, "currency": "EUR" },
  "fx": { "rate": "1.0852", "date": "2026-10-26", "source": "ECB" },
  "client_balance_after": { "amount_micros": 3550000, "currency": "USD" },
  "account_left": { "amount_micros": 22148000, "currency": "EUR" },
  "warn_low_account": false
}
```

## 8. Cuenta

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /console/audit?client=&person=&category=&days=&cursor=` · `GET /console/audit/export.csv?…` | Auditoría agrupada y su CSV | 49.1 |
| `POST /console/team/invitations` | Comprueba miembros e invitaciones pendientes | 49.2 |

Facturación, API y la Guía del partner conservan sus rutas de hoy. Facturación
gana la moneda de la cuenta (requisito 49.3).

## 9. Códigos de error nuevos

| Código | HTTP | Cuándo |
|---|---|---|
| `revision_conflict` | 412 | `If-Match` no coincide |
| `proposal_stale` | 409 | El `state_hash` de una propuesta cambió |
| `proposal_expired` | 410 | Pasaron 15 minutos |
| `gate_blocked` | 409 | La puerta no deja publicar; `blocking` dice por qué |
| `override_forbidden` | 403 | Saltar la puerta sin ser owner o admin |
| `undo_window_closed` | 409 | Pasaron 10 minutos |
| `build_budget_exhausted` | 402 | Partida «Construcción y pruebas» agotada |
| `insufficient_account` | 409 | Asignar más de lo que se puede |
| `bag_below_spent` | 409 | Bajar la bolsa por debajo de lo que queda |
| `quota_full` | 409 | Cupo de números del cliente lleno |
| `channel_test_numbers_required` | 422 | «Solo mi equipo» sin números de prueba |
| `agent_not_published` | 409 | «A todos» con el agente sin publicar (requisito 32.8) |
| `bag_empty` | 409 | «A todos» con la bolsa del cliente vacía (requisito 32.8), con la acción «Asignar saldo» o «Pedir saldo» |
| `audience_admin_only_template` | 409 | «A todos» con plantilla de solo administradores |
| `connection_not_authorized` | 409 | Activar en un agente sin conexión del cliente |
| `default_agent_required` | 409 | Archivar el agente por defecto sin elegir otro |
| `link_pending_exists` | 409 | Ya hay un enlace pendiente (con la acción «Revocar y crear») |
| `request_already_sent_today` | 429 | «Pedir saldo» o «Pedir ampliación» repetidos el mismo día |

## 10. Enmienda del 2026-10-29 (requisitos 57 a 64)

Congelado el 2026-10-29 para que la consola construya contra él mientras la API lo
implementa (fase 27). Cambiar algo aquí exige avisar a las dos partes.

### Sector (requisito 57)

- `GET /console/clients/{ref}/business` y `GET …/business/basics` devuelven
  `business.sector`:

  ```json
  {"key": "barberia_peluqueria" | "clinica" | "restaurante" | "tienda" | "servicios_profesionales" | "mayorista" | "otro",
   "label": "Barbería",
   "confidence": 0.92,
   "source": "niche" | "info" | "web" | "person" | "fallback",
   "decided_by": "system" | "person",
   "has_guide": true}
  ```

  o `null` mientras se identifica. Si hay una propuesta del sistema contra un sector
  fijado por una persona, va en las sugerencias pendientes con el puntero
  `/business/sector`, como cualquier dato (`POST /suggestions/{id}/decide`).
- `PUT …/business/basics` acepta `sector: {key, label}`; lo guarda con
  `source = "person"`, `decided_by = "person"` y `confidence = 1`. `key = "otro"` exige
  `label` (1–40). Una clave fuera de la lista → 422 `sector_unknown`.
- `GET /console/sectors` → `{"sectors": [{"key", "label"}]}`: los sectores con guía de
  Auphere, para el selector.

### Constructor del cliente (requisito 60)

- Sus propuestas de políticas y preguntas frecuentes llegan como sugerencias
  pendientes de `GET /business` (`source = "builder"`, punteros `/policies/{clave}` y
  `/faqs/-`). Se deciden con `POST /suggestions/{id}/decide`.
- `GET …/business/policies` y `GET …/business/faqs` ya existen y alimentan las
  secciones nuevas.
- `GET /console/clients/{ref}/suggested-agents` →
  `{"agents": [{"id", "name", "description", "role": "reception" | "sales" | "billing" | "support" | null}]}`.
- `POST /console/clients/{ref}/suggested-agents/{id}/dismiss` → 204. Lo descartado no
  vuelve para la misma ficha (ni para otra, D61). Un id que no es del cliente → 404
  `unknown_suggested_agent`. Listar pide `agents:read`; descartar, `agents:write`.
- «Crear este agente» abre «Nuevo agente» con `name` y `description` rellenos; no hay
  ruta nueva para crear.

### Lectura (requisito 59)

- `GET …/business/read` (o el último trabajo `client_read` en `GET /business`, como hoy)
  añade `networks: [{"network", "status": "read" | "blocked_by_network" | "failed", "reason"?}]`
  y `structured: true | false` (si se leyó JSON-LD o microdatos).

### Pruebas de varios turnos (requisito 61)

- Cada intento de `GET /agents/{agent_id}/tests` (y del detalle de una prueba) añade
  `transcript: [{"role": "customer" | "agent", "text", "actions": [string]}]` y
  `stop: "plan_done" | "goodbye" | "handoff" | "turn_limit"`.
  Implementado (T206, D70): cada prueba trae `transcript` y `stop` de la pasada que
  se enseña (la primera que falló o, si ninguna, la primera) y `attempts: [{attempt,
  passed, transcript, stop}]` de la última ejecución.
- Las pruebas del sector de una guía generada llevan `origin: "generated"`; las
  demás, su `kind` (T201).
- `POST /agents/{agent_id}/test-runs` devuelve además `estimate: Money` antes de
  encolar si se pide con `dry_run: true`. Implementado (D71): `200 {tests, estimate:
  Money | null, calls: {agent, customer_sim, judge}, unknown_prices: [model]}`, sin
  encolar nada; `estimate` es `null` si falta el precio de algún modelo.

### Canal (requisito 63.1)

- `GET …/channels/{channel_id}` (`ChannelPage`) añade `method: "coexistence" |
  "cloud_api" | null`: cómo se conectó el número, para la cabecera del canal; `null`
  si no se sabe (D56 y D64).

### Modelos (requisito 64)

- `PUT`/`PATCH` de la política de modelo desde la consola → 409 `model_policy_managed`.
  En concreto: `PATCH …/agents/{id}/draft` con un `spec` cuya `model_policy` no es la
  del agente, y `POST …/agents/{id}/quality/check` (D64).

| Código | HTTP | Cuándo |
|---|---|---|
| `sector_unknown` | 422 | Clave de sector fuera de la lista |
| `model_policy_managed` | 409 | Cambiar la política de modelo desde la consola (requisito 64) |
| `tool_retired` | 422 | Una herramienta retirada (`booking.*`, spec 048) en un borrador |

## 11. Enmienda del 2026-10-30 · Solo lo que tenemos (requisito 65)

Congelado el 2026-10-30 para que la consola (T228) construya contra él mientras la
API lo implementa (T227). Cambiar algo aquí exige avisar a las dos partes.

### Una capacidad que falta

Una sola forma, en el borrador, en el resultado del trabajo del constructor y en el
copiloto:

```json
{
  "kind": "integration" | "module" | "tool" | "action",
  "key": "quickbooks",
  "label": "quickbooks",
  "reason": "integration_unknown" | "module_off" | "not_linked" | "tool_unknown" | "no_tool",
  "source": "skill" | "connection_request" | "tool" | "text",
  "pointer": "/procedures/0/steps" | null
}
```

- `kind`:
  - `integration`: una integración que no es un conector ofrecido. El constructor
    o el copiloto la propusieron en una habilidad o en una petición de conexión.
  - `module`: un módulo del cliente apagado. Hoy solo `reservas`, que no es un
    conector y nunca se «conecta».
  - `tool`: un nombre de herramienta que no existe en el catálogo.
  - `action`: un texto del agente promete una acción que ninguna de sus
    herramientas hace (65.5): `book`, `modify_booking`, `charge`, `collect`,
    `invoice`, `order`, `modify_order`, `send_media`, `remind` o `catalog`.
- `label`: en español, listo para ir detrás de «No tenemos herramienta para: ».
  Ejemplos: `"emitir facturas"`, `"quickbooks"`, `"la agenda (Reservas no está
  activo para este cliente)"`.
- `reason`:
  - `integration_unknown`: no es un conector ofrecido;
  - `module_off`: el módulo está apagado;
  - `not_linked`: el catálogo de Meta del canal no está enlazado;
  - `tool_unknown`: la herramienta no existe;
  - `no_tool`: ninguna herramienta del agente lo hace.
- `pointer`: dónde está la promesa en el AgentSpec (solo `kind = "action"`);
  `null` en los demás.

**El agente se queda con su alternativa, no con la promesa** (65.4): lo que falta
no entra en el AgentSpec, y el prompt compilado dice que pase a una persona lo
que no puede hacer (65.6). Nada de esto genera nunca «Conectar {X}».

### Dónde llega

| Respuesta | Campo | Qué trae |
|---|---|---|
| `GET /console/jobs/{job_id}`, trabajo `agent_draft` hecho (`start: describe`) | `result.missing_capabilities: MissingCapability[]` | Lo que el constructor no pudo poner y las promesas sin herramienta del borrador recién escrito |
| `GET`, `PATCH` y `DELETE …/agents/{agent_id}/draft` (`AgentDraftOut`) | `missing_capabilities: MissingCapability[]`, siempre presente (`[]` si nada falta) | Lo que dejó fuera el constructor al crear el agente (`integration`, `module`, `tool`), guardado en la versión; lo que se quitó al leer o escribir un borrador de antes (ver abajo); y las promesas sin herramienta del AgentSpec **actual** (`action`), calculadas en cada lectura. Cada capacidad sale una vez |
| `POST …/agents/{agent_id}/copilot` | `missing_capabilities: MissingCapability[]`, siempre presente | Lo que la petición necesitaba y no tenemos. El copiloto lo dice en `text` y no propone esa parte |

- `result.connect` del trabajo `agent_draft` sigue con su forma (`[{integration,
  reason}]`), pero solo con conectores ofrecidos: nunca `reservas` ni una
  integración inventada.
- «Desde una plantilla» responde como hoy (`DraftJobOut`, `status: "done"`). Lo
  que falte se lee en el borrador.

### Borradores de antes de la enmienda (añadido el 2026-10-30)

Un agente estructurado creado antes de la enmienda puede llevar una habilidad o una
`connection_request` con algo que no es un conector ofrecido. La consola nueva no
edita ninguna de las dos, así que la API lo resuelve sola y **nunca rechaza un
cambio por eso**:

- `GET …/draft` devuelve el `spec` sin ellas y las lista en `missing_capabilities`.
- `PATCH …/draft` con `spec` las quita aunque vengan en el documento, guarda el
  resto, las anota en la versión y responde `200`. No hay `422
  integration_unknown`.
- Las propuestas del copiloto, de las correcciones y de las sugerencias parten del
  mismo documento sin ellas, y su `state_hash` también.
- La puerta tampoco bloquea por ellas.

### Pruebas del sector que no aplican (65.8)

- Al añadir las pruebas del sector, cada prueba que necesita una acción que las
  herramientas del agente no hacen llega a `GET …/agents/{agent_id}/tests` con
  `not_applicable_reason` relleno, sin que nadie lo marque. El valor va **sin**
  «No aplica:» delante, que lo pone la consola. Por ejemplo: «Este agente no tiene
  herramienta para reservar citas.».
- Cuenta como «No aplica» a todos los efectos: no bloquea la puerta.
- Una persona puede volver a activarla con `PATCH …/tests/{id}`
  (`not_applicable_reason: ""`), como hoy.

### La puerta

- **Promesa sin herramienta** (65.5):
  - `GET …/agents/{agent_id}/review` da el hallazgo `promises_without_tool` con
    `severity: "block"` en un agente `structured`. En uno de antes
    (`instructions`) sigue en `"warn"`.
  - Su `fix` pasa a `{"kind": "edit", "pointer": "<el texto que promete>"}`. No hay
    integración que conectar: se arregla quitando la promesa.
  - Al publicar, sale en `gate.overridable` del `409 gate_blocked` como
    `{"condition": "review", "code": "promises_without_tool", "message", "pointer"}`.
    `pointer` lleva al texto que promete, para «Arreglar en el borrador». Cualquier
    bloqueante de la revisión con puntero lo trae. Lo salta solo un owner o un admin
    con motivo, como cualquier bloqueante de la revisión.
- **Habilidades que dependen de algo que no es un conector**: el hallazgo
  `skill_without_integration` de una habilidad sobre `reservas` (módulo que
  enciende Auphere) o sobre el catálogo de Meta (se enlaza en Canales) llega con
  `fix: null` y un `message` que lo dice. Nunca lleva a Conectores
  (`kind: "link"`, `target: "integrations"`). Solo lleva ahí un conector de verdad.
- **Sin pruebas aplicables** (65.9): un agente `structured` sin ninguna prueba
  aplicable no se publica. El `409 gate_blocked` lo trae en `gate.hard`, que nadie
  salta: `{"condition": "critical_tests", "code": "no_applicable_tests",
  "message": "Este agente no tiene ninguna prueba que aplique: añade una antes de
  guardar."}`.

### Herramientas de un agente estructurado (65.10)

- `PUT /console/clients/{ref}/tools` (con o sin `?agent=`) sobre un agente cuya
  versión tiene un AgentSpec `structured` → `409 {"code": "structured_agent"}`.
  Las herramientas se cambian en el AgentSpec (`PATCH …/draft` con `spec`), que
  pasa el validador.
- `PATCH …/agents/{agent_id}/draft` con `tools` y sin `spec`, sobre un agente así →
  el mismo `409 structured_agent`.
- `POST /console/clients/{ref}/agent/versions` con `tools`, sobre un agente así →
  el mismo `409 structured_agent` (T217). Sin `tools` (solo el texto, lo que manda
  la consola) sigue como estaba.
- Las rutas de plantillas de la consola de antes, en un partner con la consola
  nueva:
  - `POST /console/clients` con `seed_template` → `422 seed_template_retired`;
    no se crea nada;
  - `POST /console/clients/{ref}/agent/from-seed` → `410 seed_template_retired`;
  - `POST /console/clients/{ref}/agents` con `seed_template` → `410
    seed_template_retired`.

  Un agente desde una plantilla se crea con `POST …/agents/draft-jobs`
  (`start: "template"`). La consola nueva no usa ninguna de las tres.

### Sugerencias de agentes (65.7)

- `GET /console/clients/{ref}/suggested-agents` no cambia de forma. `role` sigue
  siendo `"reception" | "sales" | "billing" | "support" | null`, pero:
  - `null` es lo normal en un agente que no encaja en ningún patrón;
  - el constructor puede proponer cualquier papel o ninguno; uno fuera de esos
    cuatro llega como `null`;
  - la consola no lo exige, no lo usa para decidir nada y trata cualquier otro
    valor como `null`.
- No llega ninguna sugerencia cuya tarea principal necesite una capacidad que el
  cliente no tiene. Por ejemplo, «Recepción para citas» con Reservas apagado: se
  sugiere uno que atienda y pase las citas al equipo, o ninguno.
- «Crear este agente» sigue abriendo «Nuevo agente» con `name` y `description`.

### Códigos nuevos

| Código | HTTP | Cuándo |
|---|---|---|
| `integration_unknown` | — | Solo como `missing_capabilities[].reason`: una habilidad o una petición de conexión con una integración que no es un conector ofrecido. La API la quita y la anota; ninguna ruta de la consola responde un error con este código |
| `facts_unavailable` | — / 503 | La ficha del negocio no se pudo leer y no se escribe ningún borrador. El trabajo `agent_draft` queda `failed` con este código. `POST …/agents/draft-jobs` con `start: "template"` responde 503. La consola dice que no se pudo leer la ficha y ofrece reintentar. No ofrece «Desde una plantilla», que también la lee |
| `builder_unavailable` | — | Como hoy. Ahora también cuando el modelo no devuelve instrucciones: ya no sale un borrador genérico |
| `promises_without_tool` | 409 | Bloqueante de la revisión en `gate_blocked` (`overridable`) |
| `no_applicable_tests` | 409 | En `gate_blocked` (`hard`): un agente `structured` sin ninguna prueba aplicable |
| `structured_agent` | 409 | `PUT …/tools`, o `PATCH …/draft` o `POST …/agent/versions` con `tools`, sobre un agente con AgentSpec `structured` |
| `seed_template_retired` | 410 / 422 | Las rutas de plantillas de la consola de antes, en un partner con la consola nueva |
