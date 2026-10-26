# Modelo de datos — spec 047

Tablas nuevas y cambios a tablas que ya existen. Reglas para todas las tablas
por cliente (garantía 1; memoria del repo «una FK no pasa por la RLS»):

- `tenant_id uuid NOT NULL`, `ENABLE` + `FORCE ROW LEVEL SECURITY`, con una
  política `USING` y `WITH CHECK` sobre `current_setting('app.tenant_id')`;
- `UNIQUE (tenant_id, id)` y **FK compuestas** `(tenant_id, x_id)` hacia toda tabla
  de cliente;
- grants del rol de la aplicación;
- las cubren los barridos `test_21`/`test_22` de `tests/isolation/` (requisito 56.1).

Las tablas de un agente añaden `agent_id` con FK compuesta `(tenant_id, agent_id)`
y entran en el barrido de la garantía 9. Las del partner se alcanzan por
`partner_id` en la API de la consola. Las de plataforma no llevan datos de
clientes y solo las escribe el admin.

Importes en `bigint` de cien milésimas de su moneda (`*_micros`). Precios del
negocio en unidades menores ISO 4217 (`*_minor`). Horas del negocio en minutos
desde la medianoche del día que abre (research D15).

Migraciones: la serie empieza en `0175` (cabeza de hoy:
`0174_reservation_calendars`) y va por olas (`plan.md`). Cada migración es
reversible, y lleva su prueba en `tests/integration/test_migration_reversibility.py`
y, si mueve datos, la suya propia, como `test_migration_0170_canonical_business_hours.py`.
Las FK compuestas se declaran con el ayudante `_tenant_fk` (`db/models/reservation.py:100`).

---

## 1. El cliente y su ficha

### `tenants` (existe) — cambios

| Columna | Tipo | Nota |
|---|---|---|
| `status` | enum | Se separa el ciclo de vida (`active`, `paused`, `archived`) de la preparación. `provisioning` deja de depender de tener agente y canal; los clientes en `provisioning` migran a `active` (requisito 4.7) |
| `business_hours`, `business_hours_label` | — | Pasan a ser **proyecciones** escritas por el servicio de horario en la misma transacción, hasta que sus lectores lean la ficha. Después se retiran (research D15) |

### `business_profiles` (nueva, 1:1 con el cliente)

| Columna | Tipo | Regla |
|---|---|---|
| `tenant_id` | uuid PK, FK → `tenants` | |
| `niche` | text | 2–80 |
| `info` | text | ≤ 2.000; dato no confiable (§III) |
| `website` | text null | URL normalizada |
| `country` | char(2) | ISO 3166-1 |
| `timezone` | text | Validada con `zoneinfo` |
| `price_currency` | char(3) | ISO 4217 |
| `eu_only` | bool | Por defecto, cierto si el país es de la UE o del EEE |
| `sovereign` | bool | Solo el admin |
| `policies` | jsonb | `{cancellation, payments, deposit, no_show}`, cada una ≤ 1.000 |
| `content_rev` | bigint | Sube con **cualquier** cambio de la ficha; entra en la clave de compilación (§3) |
| `created_at`, `updated_at` | timestamptz | |

### `business_sections` (nueva)

Una fila por cliente y sección. Sirve para `If-Match` y para el estado de cada sección.

| Columna | Tipo | Regla |
|---|---|---|
| `tenant_id`, `section` | PK | `basics`, `locations`, `hours`, `special_dates`, `services`, `policies`, `faqs`, `sources`, `links` |
| `revision` | int | Sube con cada escritura de la sección |
| `state` | enum | `complete`, `read_pending`, `pending`, `optional` (requisito 8.5) |
| `updated_at`, `updated_by_kind`, `updated_by_id`, `updated_origin` | | |

### `business_locations` (nueva)

`tenant_id`, `id`, `name` (1–80), `address` (≤ 300), `phone_e164`, `archived_at`,
`archived_by`. `UNIQUE (tenant_id, id)`.

### `business_schedules`, `business_shifts` (nuevas)

- **`business_schedules`**: `tenant_id`, `id`, `location_id` (null = la del
  negocio; FK compuesta) y `layout` (`blocks` o `daily`).
  `UNIQUE NULLS NOT DISTINCT (tenant_id, location_id)`: uno por negocio y uno por sede.
- **`business_shifts`**: `tenant_id`, `id`, `schedule_id` (FK compuesta),
  `weekday` (0 = lunes … 6), `open_min` (0–1.439) y `close_min` (1–2.880).
  - `CHECK (close_min > open_min AND close_min - open_min <= 1440)`.
  - Como mucho 6 por día: lo valida el servicio y lo prueba un test.

### `business_special_dates`, `business_special_shifts` (nuevas)

- **`business_special_dates`**: `tenant_id`, `id`, `location_id` null, `name` (≤ 80),
  `date_from`, `date_to` (`CHECK date_to >= date_from`), `closed`, `archived_at`.
- **`business_special_shifts`**: `tenant_id`, `id`, `special_date_id`, `open_min` y
  `close_min`, con los mismos CHECK.

La fecha especial manda desde la apertura del turno de ese día (casos límite).

### `business_faqs` (nueva)

`tenant_id`, `id`, `q` (≤ 300), `a` (≤ 2.000), `suggested` (bool) y `archived_at`.
Las preguntas propias de un agente van en su AgentSpec.

### `business_links` (nueva)

`tenant_id`, `id`, `network` (`web`, `instagram`, `facebook`, `tiktok`,
`linkedin`, `youtube`, `x`, `threads`), `url` y `handle`.
`UNIQUE (tenant_id, network, coalesce(handle, url))`.

### `business_field_provenance` (nueva)

Procedencia **vigente** de cada dato.

| Columna | Tipo | Regla |
|---|---|---|
| `tenant_id`, `pointer` | PK | Puntero JSON dentro del ClientSpec |
| `source` | enum | `person`, `web`, `document`, `social`, `migrated`, `builder`, `inbox_correction`, `import` |
| `actor_kind`, `actor_id`, `origin` | | `origin`: `console`, `lite_web`, `app`, `admin`, `api` o `system` |
| `source_url`, `translated_from` | text null | |
| `review` | enum | `pending` («Leído de la web · revísalo»), `confirmed` |
| `at` | timestamptz | |

### `business_changes` (nueva) — historial y deshacer

`tenant_id`, `id`, `section`, `kind` (`edit`, `read_applied`, `builder_applied`,
`correction`, `migration`, `import`, `undo`), `before` y `after` (jsonb), actor,
`origin`, `at`, `undone_at`, `undone_by` y `undo_of` (id).

Deshacer aplica `before` si nadie escribió la sección después. Si alguien
escribió, responde `412` con lo que cambió.

### `business_suggestions` (nueva) — lo leído que no se aplicó solo

`tenant_id`, `id`, `pointer`, `proposed_value` (jsonb), `current_value` (jsonb),
`source`, `source_url`, `translated_from`, `created_at`, `decided_at`,
`decided_by` y `decision` (`accepted`, `edited`, `discarded`).

Sin caducidad. Recoge dos casos:
- los datos que contradicen un valor escrito por una persona (requisito 5.8);
- las sugerencias «Sugerido · confirma» (requisito 18.3).

---

## 2. Servicios

### `reservation_services` (existe, spec 043) — cambios

| Columna | Tipo | Regla |
|---|---|---|
| `description` | text null | ≤ 1.000 |
| `bookable` | bool | Por defecto, cierto |
| `duration_min` | — | Pasa a nullable. `CHECK (NOT bookable OR duration_min BETWEEN 5 AND 480)` |
| `price_kind` | enum | `none`, `free`, `amount` |
| `price_amount_minor`, `price_currency` | bigint, char(3) | `CHECK (price_kind <> 'amount' OR price_amount_minor IS NOT NULL)` |
| `archived_at` | timestamptz | «Eliminar» archiva; las reservas pasadas conservan el nombre |

### `agent_services` (nueva)

`tenant_id`, `agent_id`, `service_id`. PK `(tenant_id, agent_id, service_id)`,
con FK compuestas a `agents` y a `reservation_services`.

### `agents` (existe) — `serves_all_services bool NOT NULL DEFAULT true`

Las herramientas de servicios y de Reservas filtran por `serves_all_services` o
por `agent_services` (requisito 11.4, garantía 9).

---

## 3. Agentes, versiones y compilaciones

### `agents` (existe) — cambios

| Columna | Tipo | Regla |
|---|---|---|
| `lifecycle` | enum | `draft`, `published`, `paused`, `archived`. Sustituye a `status` (`active` pasa a `published` si tiene versión activa y a `draft` si no; `archived` se queda) |
| `pause_reason` | enum null | `manual`, `no_balance`, `agent_cap`, `client_paused`, `client_archived` |
| `paused_at`, `paused_by_kind`, `paused_by_id`, `paused_origin` | | |
| `before_pause` | jsonb null | Lo que hay que devolver al reanudar |
| `is_default` | bool | `UNIQUE (tenant_id) WHERE is_default AND lifecycle <> 'archived'` |
| `is_reception` | bool | P3 |
| `monthly_cap_micros` | bigint null | En la moneda de la bolsa del cliente |
| `draft_revision` | int | Para `If-Match` del borrador |

### Versiones de agente (`agent_configs`, existe) — cambios

`AgentConfigStatus` ya es `staged` (el borrador), `active` (la publicada) o
`archived` (las anteriores), y `UNIQUE (tenant_id, version)` numera por cliente.
Se mantiene, y se añade:

| Columna | Tipo | Regla |
|---|---|---|
| `spec` | jsonb | AgentSpec v1 (`contracts/agent-spec.schema.json`) |
| `agent_version_number` | int | `UNIQUE (tenant_id, agent_id, agent_version_number)`; «v{n} de {agente}». El `version` de cada cliente no cambia |
| — | índice | Único parcial `(tenant_id, agent_id) WHERE status = 'staged'`: como mucho un borrador por agente |
| `base_version_id` | uuid null | La versión de la que partió |
| `note`, `published_by`, `published_at` | | |
| `gate` | jsonb | Resultado de la puerta |
| `override_reason` | text null | Solo owner o admin |
| `undo_until` | timestamptz null | 10 minutos tras publicar |
| `system_prompt_rendered` | — | Sigue siendo **la verdad del runtime** (constitución). Cada compilación nueva de la versión activa la reescribe en la misma transacción |

`policies.admin_access` pasa al AgentSpec (`team_access`). La audiencia pasa al
canal (§5). `policies.console.schedule` migra a la ficha y sale de la versión.

### `agent_version_compilations` (nueva)

| Columna | Tipo | Regla |
|---|---|---|
| `tenant_id`, `id` | | |
| `agent_config_id` | uuid | FK compuesta |
| `business_rev`, `knowledge_rev` | bigint | Revisiones de la ficha y del conocimiento del agente usadas |
| `tools_hash` | char(64) | |
| `family_variant` | text null | Variante por familia de modelo (requisito 16.3) |
| `prompt` | text | Ya renderizado (garantía 5) |
| `sha256` | char(64) | |
| `created_at` | | |

`UNIQUE (tenant_id, agent_config_id, business_rev, knowledge_rev, coalesce(family_variant, ''))`.

Es la **historia** de las compilaciones: qué prompt respondió cada turno, por su
`sha256`. El runtime no la lee; lee `system_prompt_rendered`. La ficha y el
conocimiento van dentro como bloques de datos vallados, separados de las
instrucciones (§III).

---

## 4. Constructor, propuestas, pruebas y puerta

### `jobs` (nueva) — trabajos largos

`tenant_id`, `id`, `agent_id` null, `kind` (`client_read`, `client_builder`,
`agent_draft`, `tests`, `publish`, `fix`, `copilot`, `quality_check`,
`suggestions`), `status` (`queued`, `running`, `done`, `failed`), `progress`
(jsonb: los bloques ya escritos y el paso actual), `questions` y `answers`
(jsonb), `result` (jsonb), `error_code`, `cost_micros`, `created_by`,
`created_at` y `finished_at`.

Un trabajo de `publish` guarda además `draft_revision` y el resultado de la puerta.

### `proposals` (nueva)

Hoy las propuestas del Companion viven en el esquema `companion`, atadas a sus
hilos (`db/models/companion.py:231`). El constructor no depende del módulo
`companion` (requisito 15.1), así que sus propuestas van en una tabla propia, que
reutiliza la lógica de `companion/tools/proposals.py` (`Proposal`,
`canonical_hash`) y de `actions.py` (`stage_action`, `apply_action`,
`verify_action`), sacada a `services/proposal_state.py`.

| Columna | Tipo | Regla |
|---|---|---|
| `tenant_id`, `id` | | |
| `agent_id` | uuid null | FK compuesta |
| `kind` | enum | `agent_spec_patch`, `client_spec_patch`, `test_add`, `fix`, `channel_config_patch` |
| `author` | enum | `builder`, `copilot`, `suggestion`, `correction` |
| `diff` | jsonb | El parche (`client-spec.schema.json#/$defs/patch` o su equivalente del AgentSpec) |
| `state_hash` | char(64) | `canonical_hash` del estado sobre el que se hizo |
| `status` | enum | `open`, `applied`, `rejected`, `expired`, `stale` |
| `id` | uuid | uuid5 determinista del contenido y del `state_hash`, con UPSERT: proponer dos veces lo mismo no crea dos propuestas (§IV) |
| `expires_at` | timestamptz | Creación + 15 min |
| `decided_by`, `decided_at` | | |

### `agent_test_suites`, `agent_tests` (nuevas)

- **`agent_test_suites`**: `tenant_id`, `id`, `agent_id` (único) y `revision`.
- **`agent_tests`**:
  - `tenant_id`, `id`, `suite_id`;
  - `kind`: `case`, `sector`, `person`, `conversation` o `correction`;
  - el contenido: `name`, `persona`, `first_message`, `plan`, `expected_state`
    (jsonb) y `criteria` (jsonb: dimensiones);
  - `critical` (bool) y `not_applicable_reason` (text null);
  - `sector_test_ref` (`sector@versión#clave`) y `stale` (bool);
  - `created_by_kind` y `archived_at`.

### `agent_test_runs`, `agent_test_results` (nuevas)

- **`agent_test_runs`**: `tenant_id`, `id`, `agent_id`, `agent_config_id`,
  `model_policy` (jsonb), `scope`, `reason` (`manual`, `publish`, `fix`,
  `business_change`, `certification`), `status`, `paid_by` (`partner` o
  `auphere`) y `cost_micros`.
- **`agent_test_results`**: `tenant_id`, `id`, `run_id`, `test_id`, `attempt`
  (1–3), `passed` (bool null = «No sé»), `dimensions` (jsonb), `explanation`,
  `final_state` (jsonb) y `transcript` (jsonb, sintético: no hay datos de
  clientes finales).

### `agent_reviews` (nueva)

`tenant_id`, `id`, `agent_config_id`, `findings` (jsonb: `{code, severity:
block|warn, message, fix}`) y `created_at`. Cada hallazgo sale de una comprobación
real (requisito 22.3).

### `sector_test_catalog` (nueva, plataforma)

`sector_key`, `version`, `tests` (jsonb, 12 por sector), `published_at` y
`published_by`. PK `(sector_key, version)`.

### `builder_eval_runs` (nueva, plataforma)

`id`, `bank_version`, `results` (jsonb), `validator_first_pass_pct`,
`sector_pass_unedited_pct`, `draft_p90_ms`, `created_at` y `created_by`.

---

## 5. Canales

### `channels` (existe) — cambios

`ChannelStatus` (`channel_status`) ya es `active`, `paused`, `degraded` o
`disconnected`, pero hoy nada escribe `paused`. Se mantiene: `degraded` es el
«Con problemas» de la interfaz.

| Columna | Tipo | Regla |
|---|---|---|
| `problem_reason` | enum null | `quality`, `auth_expired`, `coexistence_inactive`, `meta_error` (cuando `status = 'degraded'`) |
| `audience_mode` | enum | `unset`, `team_only`, `everyone` |
| `config_revision` | int | `If-Match` |
| `paused_by_kind`, `paused_by_id`, `paused_origin`, `paused_at` | | |
| `coexistence` | bool | Número en coexistencia (`is_on_biz_app`) |
| `config` | jsonb | Gana `wait_message` y `escalation_summary`. Reconectar **combina** en lugar de sobrescribir (requisito 30.7) |

El resolutor de números reconoce `active`, `paused` y `degraded` (requisito 2.2).
Para eso, una migración redefine la función `resolve_channel_tenant` (SECURITY
DEFINER, hoy con `status='active'`, `0002_rls_policies.py:73-89`). El estado
visible se deriva (`contracts/events.md` §1; su código `problem` es el
`degraded` guardado).

### `channel_audience_numbers` (nueva)

`tenant_id`, `id`, `channel_id`, `kind` (`test` o `exception`), `phone_e164` y
`label`. `UNIQUE (tenant_id, channel_id, kind, phone_e164)`.

### `channel_escalation_recipients` (nueva)

`tenant_id`, `id`, `channel_id`, `name`, `via` (`whatsapp`, `email` o `inbox`),
`phone_e164`, `email`, `client_user_id` (null = toda la Bandeja). Un CHECK exige
el campo que pide cada vía. Como mucho 10 por canal.

### `channel_config_changes` (nueva)

`tenant_id`, `id`, `channel_id`, `before`, `after`, actor, `origin`, `at`,
`undo_until` y `undone_at`.

### Enlaces del dueño (tabla de la spec 040, existe) — cambios

Gana `agent_id` (FK compuesta), `mode` (`coexistence`, `cloud_api` o
`whatsapp_login`) y `revoked_at`. Un índice único parcial deja como mucho un
enlace pendiente por agente. El token se guarda solo como huella.

### `whatsapp_login_beta_countries` (nueva, plataforma)

`country` (PK), `enabled_at` y `enabled_by`. Un CHECK de servicio rechaza los
países de la UE y del EEE.

### Conversaciones y mensajes (existen) — cambios

- **Conversaciones**:
  - `waiting_reason`: enum con la lista cerrada de `events.md` §2;
  - `handled_by_agent_id`: Recepción;
  - `takeover_until`: eco de coexistencia;
  - `reception_hops` (smallint) y `last_turn_at`.
- **Mensajes**:
  - `origin`: `customer`, `agent`, `business_person`, `business_app_echo`,
    `history_import` o `system`;
  - `turn_id` (null hasta que un turno lo procesa: agrupación de 3 s).

### `turn_effects` (nueva)

`tenant_id`, `turn_id`, `effect`, `idempotency_key` (UNIQUE por cliente),
`result` (jsonb) y `created_at`. Una acción con efecto se ejecuta como mucho una
vez (requisito 1.3).

### `meta_reconciliation_runs` (nueva)

`tenant_id`, `id`, `channel_id`, `date`, `meta_count`, `stored_count`, `diff` y
`created_at`.

---

## 6. Integraciones y conocimiento

### `tenant_connectors` (existe) — cambios

La salud ya la dice `TenantConnectorStatus` (`pending`, `connected`, `partial`,
`needs_reauth`, `paused`, `disconnected`, `error`). Se añade `last_checked_at`.
Los ajustes repartidos (la URL de AgendaPro, WooCommerce, Amigable y los
recordatorios) pasan a la activación de cada agente. `UNIQUE (tenant_id, connector)`
sigue: una conexión por cliente y servicio.

### `agent_connector_activations` (nueva)

| Columna | Tipo | Regla |
|---|---|---|
| `tenant_id`, `id` | | |
| `agent_id`, `connector_id` | uuid | FK compuestas a `agents` y a `tenant_connectors` |
| `permission` | enum | `read`, `ask_before_write`, `read_write` |
| `settings` | jsonb | Validado con el `settings_schema` del catálogo de la integración |
| `created_by`, `created_at`, `updated_at` | | |

`UNIQUE (tenant_id, agent_id, connector_id)`. Las herramientas de un agente solo
se construyen si existe su activación (garantías 2 y 9). El permiso se traduce a
los `ConnectorToolMode` de hoy (`tenant_connector_tool_overrides`): `read` deja
solo las herramientas de lectura, y `ask_before_write` pide aprobación durable (§IV).

### Catálogo de integraciones (existe) — `settings_schema jsonb`

### Documentos de conocimiento (existe) — cambios

Ganan `agent_id` null (null = capa del negocio; FK compuesta), `removed_at`,
`removed_by` y `restore_until` (10 minutos).

### `knowledge_chunks` (nueva)

Hoy no hay fragmentos: el turno inyecta el texto entero
(`console_context.load_knowledge_block`).

| Columna | Tipo | Regla |
|---|---|---|
| `tenant_id`, `id` | | |
| `document_id` | uuid | FK compuesta |
| `agent_id` | uuid null | La capa |
| `ordinal`, `text` | | |
| `embedding` | vector(1024) | Titan v2 |
| `tsv` | tsvector | `spanish`, generado |

Índice btree `(tenant_id, agent_id)`. **Sin índice ANN**: búsqueda exacta por
cliente (research D14).

### `knowledge_revisions` (nueva)

`tenant_id`, `agent_id` null y `rev` (bigint). La subida de una fuente, quitarla o
«Enseñar» incrementa la revisión de su capa.

### Memoria del contacto (`agent_memories`, existe) — cambios

Gana `agent_id` null (null = compartida), con su FK compuesta. Un agente con
«memoria propia» lee y escribe solo filas con su `agent_id` (garantía 9). El
disparador de `agent_memory_versions` copia la columna.

### `turn_sources` (nueva)

`tenant_id`, `id`, `message_id` (la respuesta), `agent_id` y `sources` (jsonb:
`{kind: business|knowledge|instruction|tool, ref}`). Los usan el copiloto y las
sugerencias (requisito 38.3).

---

## 7. Dinero

### Cuenta del partner (`partner_wallets`, existe) — cambios

Gana `currency char(3) NOT NULL DEFAULT 'USD'`. `purchased_remaining`,
`credit_limit` y el pool incluido (`included_remaining`) no cambian. El pool **no**
entra en lo que se puede asignar. El libro de la cuenta es `usage_ledger`, que
gana los kinds de los traspasos (`LEDGER_KINDS`).

### `client_wallets` (nueva) — la bolsa

| Columna | Tipo | Regla |
|---|---|---|
| `tenant_id` | PK | |
| `currency` | char(3) | `EUR` o `USD` |
| `balance_micros` | bigint | `CHECK (balance_micros >= 0)` |
| `month` | date | Primer día del mes en curso (UTC) |
| `month_base_micros` | bigint | Saldo al empezar el mes + lo asignado en el mes (research D27) |
| `month_spent_micros` | bigint | |
| `refill_up_to_micros` | bigint null | |
| `alert_low_enabled` | bool | |
| `low_alerted_month`, `not_enough_alerted_month`, `empty_alerted_on` | | Deduplicación de avisos |
| `revision` | int | |

### `client_wallet_entries` (nueva) — el lado del cliente del libro

`tenant_id`, `id`, `transfer_id` null, `kind` (`assign`, `lower`, `move_in`,
`move_out`, `refill`, `debit_turn`, `currency_change`, `migration`),
`amount_micros` (con signo), `balance_after_micros`, `currency`, `usage_ref`
null (el débito de un turno) y `created_at`.

### `wallet_transfers` (nueva, del partner)

| Columna | Tipo | Regla |
|---|---|---|
| `id`, `partner_id` | | |
| `kind` | enum | `assign`, `lower`, `move`, `refill`, `currency_change`, `migration` |
| `from_tenant_id`, `to_tenant_id` | uuid null | |
| `partner_amount_micros`, `partner_currency` | | El lado de la cuenta |
| `client_amount_micros`, `client_currency` | | El lado de la bolsa |
| `fx_rate`, `fx_date` | numeric(18,8), date | Del BCE |
| `idempotency_key` | text | `UNIQUE (partner_id, idempotency_key)` |
| `actor_id`, `created_at` | | |

Cada traspaso escribe, en una sola transacción, su asiento en el libro de la
cuenta (el de hoy, con `transfer_id`) y su asiento gemelo en
`client_wallet_entries`. El cuadre diario comprueba la invariante
cuenta + bolsas + gastado (requisito 43.9).

### `agent_monthly_spend` (nueva)

`tenant_id`, `agent_id`, `month`, `spent_micros`, `warned_at` y `reached_at`.
PK `(tenant_id, agent_id, month)`. La puerta del turno la lee para el tope del
agente.

### `fx_rates` (nueva, plataforma)

`date`, `base` (`EUR`), `quote`, `rate` y `fetched_at`. PK `(date, base, quote)`.

### `balance_requests` (nueva)

`tenant_id`, `id`, `requested_by`, `note` (≤ 280) y `created_at`. Un índice único
sobre `(tenant_id, (created_at AT TIME ZONE 'UTC')::date)` deja una petición al
día por cliente.

### `partner_build_budget` (nueva, del partner)

`partner_id`, `month`, `cap_micros`, `spent_micros`, `warned_at`,
`exhausted_at`. `partners.build_budget_default_micros` (por defecto, 50 en la
moneda de la cuenta). `build_budget_requests`: `partner_id`, `id` y `created_at`
(una al día).

### `usage_records` (existe) — cambios

Ganan:
- `task`: un código de la taxonomía;
- `route_decision_id`: uuid;
- `line`: la partida (`conversations`, `build`, `companion`).

El gasto de Meta sale de `messages.cost_usd`. `source` se conserva; `line` se
deriva de él al escribir.

---

## 8. Modelos y router

### `model_profiles` (existe: una fila por despliegue) — cambios

Ganan:
- **identidad**: `provider`, `route`, `region`, `family`;
- **residencia y retención**: `residency` (`eu`, `us`, `global`),
  `zero_retention`, `retention_how`;
- **licencia y contrato**: `license_id`, `license_url`, `license_read_at`,
  `contract_dpa`, `subprocessor_listed`;
- **ciclo de vida**: `status` (`draft`, `certifying`, `active`, `retiring`,
  `retired`, `unavailable`) y `retire_after`;
- **capacidades y cuota**: `capabilities` (jsonb, `router-and-catalog.md` §2) y `quota` (jsonb).

Las listas `RESPOND_MODELS` y `HOP_MODEL_IDS` del código pasan a datos.

### `model_prices` (nueva, plataforma)

`deployment_id`, `valid_from`, `input`, `cache_read`, `cache_write`, `output`,
`audio_minute`, `image`, `surcharge` (jsonb), `source_url` y `currency`.
PK `(deployment_id, valid_from)`.

### `router_taxonomy`, `router_profiles` (nuevas, plataforma)

- **`router_taxonomy`**: `version` y `tasks` (jsonb).
- **`router_profiles`**: `profile` (`auto`, `economy`, `balanced`, `max`,
  `platform`), `version`, `policy` (jsonb), `published_by`, `reason` y
  `published_at`. PK `(profile, version)`.

### `model_task_certifications` (nueva, plataforma)

`deployment_id`, `task`, `battery_version`, `scores` (jsonb), `quality`,
`passed`, `certified_at` e `invalidated_at`. PK `(deployment_id, task, battery_version)`.

### `agent_model_certifications` (nueva, por cliente)

`tenant_id`, `id`, `agent_id`, `deployment_id`, `agent_config_id`,
`suite_revision`, `result` (jsonb), `passed`, `paid_by`, `certified_at` e
`invalidated_at`.

### `router_anomalies` (nueva)

`tenant_id`, `id`, `task`, `kind` (`reserve_model`, `no_model`, `cooldown`),
`decision_id` y `created_at`.

Las decisiones del router van al log estructurado (`llm.route_decision`), no a
una tabla: hay varias por turno. `usage_records.route_decision_id` las enlaza.

### Lista permitida del partner (`partner_model_allowlist`, existe)

No cambia: es la lista de modelos que puede usar cada partner, y ya tiene su
pantalla (`adm/partners/[id]/models`). Las asignaciones por cliente
(`tenant_model_bindings`) siguen siendo el techo del cliente.

---

## 9. Mejora y correcciones

### `agent_suggestions` (nueva)

`tenant_id`, `id`, `agent_id`, `week`, `topic` (paráfrasis sin datos
personales), `conversations_count` (≥ 5), `contacts_count` (≥ 5), `proposal_id`,
`status` (`open`, `accepted`, `discarded`), `discard_reason` y `suppress_until`
(30 días).

### `inbox_corrections` (nueva)

`tenant_id`, `id`, `conversation_id`, `message_id`, `author_client_user_id`,
`scope` (`business` o `agent`), `agent_id`, `kind` (`data` o `behavior`),
`lesson`, `paraphrase`, `pii` (jsonb), `status` (`draft`, `applied`,
`proposed`, `accepted`, `rejected`), `applied_change_id`, `proposal_id` y
`created_at`.

El partner lee `lesson` y `paraphrase`, nunca `message_id` ni el mensaje (C1).

---

## 10. Consola nueva y migración

### Activación por partner

`partners.console_v2_enabled_at` y `console_v2_enabled_by`. No se usa
`partners.console_modules` (los módulos de la spec 032), porque esto no es un
módulo que el partner ve: es un modo de la consola con estado de migración.
`partners.qa_monthly_token_cap` deja paso a `partner_build_budget` en la ola 7.

### Módulos del cliente

`ClientModule` (`panel`, `inbox`, `reservas`, `usage`) gana `agents` y `business`.
Se activan por defecto en los clientes de partners con la consola nueva.

### `migration_reports` (nueva, del partner)

`partner_id`, `id`, `kind` (`dry_run` o `activation`), `status`, `eval_diff`
(jsonb, por agente), `audience_diff` (jsonb, por número) y `created_at`.

### `wallet_migration_proposals` (nueva, del partner)

`partner_id`, `proposal` (jsonb: lo que le queda a cada cliente este mes),
`confirmed_at` y `confirmed_by`.

---

## 11. Avisos y auditoría

- **Notificaciones** (`console_notifications`, existe): `NotificationKind` gana
  los tipos de `contracts/events.md` §3, con su gravedad, su audiencia (`partner` o
  `client`) y su enlace.
- **Push** (`client_push_events`, el outbox de hoy): los tipos de §3.1.
- **Auditoría** (`audit_log` y las filas de `console_audit_vocabulary`, que se
  añaden por migración): la categoría **Negocio** y las acciones de §4, con su
  origen.

---

## 12. Transiciones

### Agente

```text
          publicar                pausar (persona | sin saldo | tope | cliente)
draft ─────────────▶ published ◀────────────────────────────▶ paused
  │                      │            reanudar (devuelve before_pause)  │
  └──── archivar ────────┴───────────────▶ archived ◀───────────────────┘
                                             │ restaurar
                                             ▼
                                           paused
```

- Sin saldo, el agente pasa a `paused` (`no_balance`) en todos los agentes
  publicados del cliente. Al volver a tener saldo se reanudan **solo** los que el
  sistema pausó por eso (requisito 27.4).
- Archivar el agente por defecto exige elegir otro antes (requisito 28.4).

### Bolsa

`assign` y `refill` suben, `lower` y `move_out` bajan, `debit_turn` baja hasta
cero. Al llegar a 0 el estado pasa a `empty` y los agentes se pausan con
`no_balance`. Al subir de 0, se reanudan.

### Propuesta

`open` → `applied` | `rejected` | `expired` (15 min) | `stale` (cambió el
`state_hash`).
