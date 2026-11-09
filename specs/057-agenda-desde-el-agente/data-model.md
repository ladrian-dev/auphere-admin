# Modelo de datos: La agenda desde el agente

**Sin tablas ni columnas nuevas.** Todo lo que la spec necesita ya tiene sitio; lo nuevo es cómo
se lee y una restricción ampliada.

## Lo que cambia

### `jobs.kind` — admite `agenda_text`

Migración `0229_agenda_from_agent` (cabeza actual: `0228_staff_calendar_connections`): además de lo de abajo, `ck_conversations_waiting_reason` admite `agenda_not_ready` (el runtime pasa la cita a una persona cuando la agenda no está lista y el agente no tiene herramienta de derivar; la bajada lo devuelve como `escalated`). Y
`ck_jobs_kind` se recrea con `agenda_text`. `JOB_KINDS` (`db/models/jobs.py`) igual. Bajada:
borra los trabajos `agenda_text` y recrea la restricción de antes.

`progress.input` del trabajo: `{agent_id, enabled, actor}`. Nunca el texto del agente.

### `proposals` — la propuesta de la agenda

Fila con `kind = 'agent_spec_patch'`, `author = 'builder'`, `job_id` del trabajo `agenda_text`,
`summary` que dice qué cambió, `diff = {"ops": [JSON Patch]}` sobre `/procedures`, `/rules`,
`/escalation`, `/skills`, `/instructions` y `/services/faqs`, `state_hash` del AgentSpec ya
cambiado. `expires_at = now() + 7 días` (plazo por llamada; el resto sigue a 15 minutos).

Cliente: `tenant_id` del contexto. RLS forzada (0187). Una abierta por agente: una propuesta nueva
de la agenda deja `stale` la anterior del mismo agente.

### `client_access.modules` — `reservas` añadido desde el agente

Sin cambio de forma. `turn_on_from_agent` añade `reservas` con `ordered_modules(also=…)` y no toca
`enabled` ni los demás módulos. Si no hay fila, la crea con `enabled = false` y el `partner_id` del
`PartnerTenant` de la ruta.

### `reservation_settings` — la primera activación

Sin cambio. `apply_choice` la crea con `apply_defaults(mode, capacity_kind)`.

### `agent_configs` — la agenda de un agente

No hay columna. **La agenda de un agente es** «su lista de herramientas contiene las 9
`reservas.*`» (en `tools` y en `spec.tools`). Estados que la consola lee:

| Estado | Borrador | Versión activa |
|---|---|---|
| `none` | sin `reservas.create` | sin `reservas.create` |
| `prepared` | con `reservas.create` | sin `reservas.create` |
| `on` | — | con `reservas.create` |

Una agenda «a medias» (alguna de las 9 apagada a mano en «Qué puede hacer») sigue siendo `on` si
lleva `reservas.create`.

### `policies.builder.missing_capabilities` — se lee contrastada

Sin migración. Se guarda igual; al leer, `missing.still_missing(items, spec, ctx)` quita lo que la
versión ya cubre (R6). `write_spec` deja de arrastrar al fusionar lo que ya no falta.

### `audit_log`

- `client_access.updated` con `after_json = {"modules", "from_agent", "mode", "capacity_kind"}`
  al encender desde un agente.
- `console.agenda.update` con `{"agent_id", "enabled", "module_turned_on"}` en cada cambio del
  interruptor.

## Lo que se calcula y no se guarda

- **`agenda_ready(session)`** (turno): módulo encendido y con modo, horario, y en servicios
  alguien en activo y algún servicio reservable; en aforo, plazas y franjas.
- **`not_ready(session, tenant_id, now)`** (revisión y pantalla): la versión completa que ya
  existe, con sus motivos.
- **`gives_appointments(cfg)`** (R5): reserva en un conector, nombra `booking.*`, o su texto
  promete `book` / `modify_booking`.
