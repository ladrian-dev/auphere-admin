# Modelo de datos — 043 Reservas

Todas las tablas son **por cliente**: `tenant_id uuid NOT NULL REFERENCES tenants(id)
ON DELETE CASCADE`, `ENABLE` + `FORCE ROW LEVEL SECURITY` y la política
`<tabla>_tenant_isolation USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (misma condición)`. Toda referencia entre tablas de cliente es
**clave foránea compuesta** `(tenant_id, x_id) → x (tenant_id, id)`: la
comprobación de una FK no pasa por la RLS (memoria `fk-no-pasa-por-rls`).
`nexus_app` recibe `SELECT, INSERT, UPDATE` (y `DELETE` solo donde se dice).

Migraciones: `0172_reservations_schema` (tablas, CHECK de módulos y de tipos de
push), `0173_reservations_tools` (catálogo de herramientas y vocabulario de
auditoría `reservations.mode_changed`). P3: `0174_reservation_calendars`. (`0170` y
`0171` son de los bugs y de la 045.)

Todas las horas se guardan en UTC (`timestamptz`); los días y horas «del
negocio» se interpretan en `tenants.timezone`.

---

## `reservation_settings` — una fila por cliente

| Columna | Tipo | Por defecto | Notas |
|---|---|---|---|
| `tenant_id` | uuid PK, FK tenants | | |
| `mode` | varchar(16) | | CHECK `services` \| `capacity`. Solo lo escribe el admin |
| `capacity_kind` | varchar(16) NULL | | CHECK `restaurant\|bar\|classes\|tours\|rooms\|spa`; NOT NULL si `mode = capacity` |
| `slot_step_minutes` | smallint | 30 | Servicios: 15 \| 30 \| 60 |
| `waitlist_enabled` | bool | true | |
| `waitlist_lead_minutes` | int | 120 | 60 \| 120 \| 240 \| 1440 |
| `agent_min_notice_minutes` | int | 60 | 0–1440 |
| `agent_max_days_ahead` | int | 60 | 1–365 |
| `reminder_enabled` | bool | true | Servicios: recordatorio 24 h |
| `confirm_enabled` | bool | true | Pedir confirmación |
| `confirm_when` | varchar(16) | `24h` | CHECK `24h\|same_day_12\|3h`. Servicios siempre `24h` |
| `release_unconfirmed` | bool | false (Aforo: true) | Solo Aforo |
| `seats` | int NULL | | Aforo. > 0 |
| `stay_minutes` | int NULL | | Aforo. 30–480, múltiplo de 15 |
| `max_party` | int NULL | | Aforo. 1–`seats` |
| `walkin_hold` | int NULL | | Aforo. 0–`seats/2` |
| `schedule` | jsonb NULL | | Aforo. Ver abajo |
| `version` | int | 1 | Concurrencia (`If-Match`) |
| `updated_by` | varchar(120) | | `client:<email>` u `operator:<email>` |
| `created_at`, `updated_at` | timestamptz | | |

`schedule` (Aforo):

```json
{"model": "shifts", "step_minutes": 30,
 "shifts": [{"name": "Comida", "from": "13:00", "to": "15:00"}, {"name": "Cena", "from": "20:00", "to": "22:00"}]}
{"model": "slots", "step_minutes": 60, "from": "12:00", "to": "23:00"}
```

`from`/`to` son la primera y la **última llegada** (inclusiva). `step_minutes`
15, 30, 60, 90 o 120 y divide `to − from`.

**Valores de partida por tipo** (del diseño):

| Tipo | Aforo | Estancia | Máx./reserva | Guardadas | Horario |
|---|---|---|---|---|---|
| `restaurant` | 64 | 90 | 10 | 6 | turnos Comida 13–15, Cena 20–22, cada 30 |
| `bar` | 80 | 120 | 12 | 16 | franjas 12–23 cada 60 |
| `classes` | 20 | 60 | 2 | 2 | turnos Mañana 7–10, Tarde 17–21, cada 60 |
| `tours` | 16 | 120 | 8 | 0 | franjas 10–18 cada 120 |
| `rooms` | 120 | 120 | 40 | 0 | franjas 10–22 cada 120 |
| `spa` | 14 | 90 | 4 | 2 | franjas 10–21 cada 60 |

## `reservation_staff` — personas del equipo (Servicios)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | `UNIQUE (tenant_id, id)` |
| `tenant_id` | uuid | |
| `name` | varchar(120) | |
| `email` | varchar(254) NULL | Para invitar a su calendario (P3) |
| `hours` | jsonb NULL | Horario semanal en la forma canónica de `services/business_hours.py`, hasta 2 tramos por día. `NULL` = el del negocio |
| `position` | int | Orden en la agenda |
| `archived_at` | timestamptz NULL | No se borra |
| `created_at`, `updated_at` | | |

## `reservation_services` — catálogo (Servicios)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | `UNIQUE (tenant_id, id)` |
| `tenant_id` | uuid | |
| `name` | varchar(120) | |
| `duration_minutes` | smallint | 15–480, múltiplo de 15 |
| `price_minor` | bigint NULL | En la unidad menor de `currency` (CLP: pesos). `NULL` = sin coste |
| `currency` | char(3) | La del negocio (`CLP` por defecto) |
| `all_staff` | bool | true = lo hace todo el equipo |
| `position` | int | |
| `archived_at` | timestamptz NULL | |

`reservation_service_staff (tenant_id, service_id, staff_id)`, PK de las tres,
FK compuestas a las dos tablas. `DELETE` permitido (es una relación, no un
registro de negocio).

## `reservations`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | `UNIQUE (tenant_id, id)` |
| `tenant_id` | uuid | |
| `mode` | varchar(16) | El modo en que se hizo. CHECK |
| `status` | varchar(16) | CHECK `pending\|confirmed\|arrived\|done\|noshow\|cancelled` |
| `starts_at`, `ends_at` | timestamptz | `ends_at > starts_at`. Servicios: inicio + duración. Aforo: inicio + estancia |
| `party_size` | smallint | ≥ 1. Servicios: 1 |
| `staff_id` | uuid NULL | FK `(tenant_id, staff_id)` → `reservation_staff`. NOT NULL en Servicios |
| `service_id` | uuid NULL | FK `(tenant_id, service_id)` → `reservation_services`. NOT NULL en Servicios |
| `service_name` | varchar(120) NULL | Copia al reservar (el servicio puede cambiar) |
| `price_minor`, `currency` | bigint NULL, char(3) NULL | Copia al reservar |
| `customer_id` | uuid NULL | FK `(tenant_id, customer_id)` → `customers`. Con teléfono, el contacto del negocio |
| `conversation_id` | uuid NULL | FK `(tenant_id, conversation_id)` → `conversations`. La del agente que reservó |
| `agent_id` | uuid NULL | FK `(tenant_id, agent_id)` → `agents` |
| `contact_name` | varchar(120) | «Sin reserva» en una llegada sin nombre |
| `contact_phone` | varchar(32) NULL | E.164 |
| `origin` | varchar(16) | CHECK `agent\|person\|waitlist\|walkin` |
| `channel` | varchar(16) | CHECK `whatsapp\|phone\|in_person` |
| `created_by_kind` | varchar(16) | CHECK `agent\|person\|system` |
| `created_by_name` | varchar(120) | Nombre de la persona o del agente |
| `note` | varchar(500) NULL | |
| `wants_earlier` | bool | En la lista de espera para adelantar (Servicios) |
| `any_staff` | bool | Le vale cualquiera (Servicios, lista de espera) |
| `arrived_at` | timestamptz NULL | |
| `cancelled_at` | timestamptz NULL | |
| `cancelled_by` | varchar(16) NULL | CHECK `customer\|business\|system` |
| `cancel_cause` | varchar(32) NULL | `mode_change`, `release_unconfirmed`, `staff_archived`… |
| `confirmation_requested_at` | timestamptz NULL | |
| `idempotency_key` | varchar(120) NULL | `UNIQUE (tenant_id, idempotency_key)` |
| `version` | int | |
| `created_at`, `updated_at` | | |

Índices: `(tenant_id, starts_at)`; `(tenant_id, staff_id, starts_at) WHERE status IN ('pending','confirmed')`;
`(tenant_id, customer_id, starts_at)`.

**Sin doble reserva**, en las escrituras (API y herramientas): dentro de la
transacción, `pg_advisory_xact_lock` sobre `hashtext('res:' || tenant_id || ':' || staff_id)`
(Servicios) o `… || ':' || fecha_local` (Aforo), y se **revalida** con la misma
función que ofrece los huecos. La base no tiene un `EXCLUDE` (exigiría
`btree_gist` en Aurora); la prueba de concurrencia es la garantía.

**Vivas** = `pending`, `confirmed`, `arrived`. Ocupan sitio y bloquean huecos.

## `reservation_events` — historial

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id`, `reservation_id` | uuid | FK compuesta |
| `kind` | varchar(32) | `created, confirmed, confirmation_requested, reminder_sent, replied_yes, replied_no, moved, cancelled, arrived, noshow, undone, done, waitlist_joined, waitlist_accepted, notified, notify_failed, released, clash` |
| `actor_kind` | varchar(16) | `agent\|person\|system\|customer` |
| `actor_name` | varchar(120) NULL | |
| `data` | jsonb | Datos estructurados (`{"from": {...}, "to": {...}}`, `{"what": "moved", "channel": "whatsapp"}`…). **Sin texto libre de nadie** |
| `created_at` | timestamptz | |

Solo `INSERT, SELECT` para `nexus_app`: el historial no se edita.

## `reservation_blocks` — bloqueos (Aforo)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid | |
| `day` | date | Local del negocio |
| `from_time`, `until_time` | time | Primera y última llegada bloqueadas (inclusivas) |
| `label` | varchar(120) | Obligatoria («Evento privado») |
| `created_by_name` | varchar(120) | |
| `removed_at` | timestamptz NULL | «Quitar» no borra |
| `created_at` | | |

## `reservation_waitlist` — lista de espera

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | `UNIQUE (tenant_id, id)` |
| `tenant_id` | uuid | |
| `mode` | varchar(16) | |
| `status` | varchar(16) | CHECK `waiting\|offered\|accepted\|removed\|expired` |
| `customer_id` | uuid NULL | FK compuesta |
| `contact_name`, `contact_phone` | | |
| `party_size` | smallint | Aforo |
| `desired_day` | date NULL | Aforo: el día; Servicios: el día o `NULL` |
| `desired_time` | time NULL | Aforo: la franja |
| `desired_until` | date NULL | Servicios «esta semana»: último día |
| `service_id`, `staff_id` | uuid NULL | Servicios. FK compuestas; `staff_id NULL` = cualquiera |
| `reservation_id` | uuid NULL | Servicios: la cita que quiere adelantar |
| `joined_by_kind` | varchar(16) | `agent\|person\|in_person` |
| `joined_by_name` | varchar(120) NULL | |
| `created_at`, `updated_at` | | |

## `reservation_offers` y `reservation_offer_candidates` — ofertas de un hueco

`reservation_offers`:

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | `UNIQUE (tenant_id, id)` |
| `tenant_id` | uuid | |
| `mode` | varchar(16) | |
| `status` | varchar(16) | CHECK `running\|filled\|empty\|stopped` |
| `starts_at`, `ends_at` | timestamptz | El hueco (Servicios) o la franja (Aforo) |
| `staff_id`, `service_id` | uuid NULL | Servicios |
| `seats` | smallint NULL | Aforo: sitio liberado |
| `source_reservation_id` | uuid NULL | La cancelada |
| `cancelled_by_name` | varchar(120) NULL | |
| `window_minutes` | smallint | 5 (Servicios) \| 15 (Aforo) |
| `max_candidates` | smallint | 5 (Servicios) \| 1 en curso (Aforo) |
| `filled_reservation_id` | uuid NULL | |
| `created_at`, `closed_at` | | |

Una sola oferta `running` por hueco: índice único parcial
`(tenant_id, starts_at, COALESCE(staff_id, '00000000-0000-0000-0000-000000000000')) WHERE status = 'running'`.

`reservation_offer_candidates`:

| Columna | Tipo | Notas |
|---|---|---|
| `offer_id`, `waitlist_id` | uuid | PK; FK compuestas |
| `tenant_id` | uuid | |
| `position` | smallint | 1..n |
| `status` | varchar(16) | CHECK `queued\|waiting\|noreply\|accepted\|late_taken\|late_won\|skipped\|stopped` |
| `sent_at`, `deadline_at`, `answered_at` | timestamptz NULL | |

## `reservation_outbox` — lo que hay que decirle al cliente final

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id`, `reservation_id` | uuid | FK compuesta (`reservation_id` NULL para ofertas: entonces `offer_id`) |
| `offer_id`, `waitlist_id` | uuid NULL | |
| `kind` | varchar(24) | `confirmation\|reminder\|ask_confirmation\|moved\|cancelled\|offer\|offer_won\|offer_lost` |
| `dedupe_key` | varchar(160) | `UNIQUE (tenant_id, dedupe_key)`: una vez por reserva y tipo |
| `status` | varchar(16) | `pending\|sent\|failed\|skipped` |
| `skip_reason` | varchar(40) NULL | `no_phone`, `no_template`, `opted_out`, `no_channel` |
| `attempts` | smallint | Tope 3 |
| `next_attempt_at` | timestamptz | |
| `message_id` | uuid NULL | El `messages.id` que salió |
| `created_at`, `updated_at` | | |

## P3: `reservation_staff_calendars` y `reservation_busy`

`reservation_staff_calendars (tenant_id, staff_id PK, calendar_id varchar(255),
last_sync_at, last_error varchar(200))` — qué calendario de la cuenta de Google
del cliente es de cada persona. `reservation_busy (id, tenant_id, staff_id,
starts_at, ends_at, source 'google', synced_at)` — solo intervalos, sin título.
`reservations.external_event_id varchar(255) NULL` — el evento «Ocupado» que se
escribió.

## Columnas en tablas que ya existen

- `client_access.modules`: el CHECK pasa a
  `modules <@ ARRAY['panel','inbox','usage','reservas']`.
- `client_phones.notice_kinds` y `client_push_events.kind`: los CHECK ganan
  `reservas.agent_change`, `reservas.cancelled_today`,
  `reservas.waitlist_accepted`.

## Máquina de estados

```
            ┌──────── confirm ────────┐
 (agente) pending ──────────────────► confirmed ◄── (negocio, lista de espera)
     │  │                               │   │  │
     │  └─ release (Aforo, 1 h antes) ──┼───┼──┼──► cancelled ◄── cancel
     │                                  │   │  └─ arrive (Aforo, hoy, ≥ hora−30 min) ─► arrived ─(estancia)─► done
     │                                  │   └──── noshow (hoy, ≥ hora) ──────────────► noshow
     └─(Servicios: fin pasado)──────────┴────────(Servicios: fin pasado)─────────────► done
 undo: arrived|noshow ─► confirmed (solo hoy; no en llegada sin reserva)
 walkin: nace arrived
```
