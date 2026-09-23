# Modelo de datos: la ficha de cliente y el consumo, por flujo

Solo lo que cambia. Todo lo demás (clientes, versiones del agente, canales,
asignaciones, cartera, conectores, avisos) ya existe con su RLS; ver
`nexus/architecture/console-map.md`.

## Sin migraciones de esquema

Ninguna tabla ni columna nueva. Todo lo que la spec pide se **deriva** de
columnas que ya existen:

| Concepto de la spec | De dónde sale | Tenant / partner |
|---|---|---|
| Sector del cliente | `agent_configs.seed_template_ref` de la versión activa (o del borrador) → `_vertical()` | tenant (`agent_configs.tenant_id`, RLS) |
| Estado de puesta en marcha | `agent_configs.status = ACTIVE` · `channels` con `customer_facing_channel()` y `status = ACTIVE` · `quota_state` · `tenants.status = ACTIVE` | tenant |
| Cupo restante | `partner_allocations.cap / remaining` | partner + tenant (FORCE RLS por partner, spec 016) |
| Borrador pendiente y sus secciones | dos filas de `agent_configs` (borrador y activa): `policies`, `tools`, `runtime_skills`, `system_prompt_rendered`, `model_bindings` | tenant |
| Capacidad | `tools` (catálogo común) + `skills_catalog` (bundle) + estado por tenant en `agent_configs.tools` / `runtime_skills` | catálogo común; estado por tenant |
| Conversaciones de 7 días | `conversations.started_at` por tenant | tenant |
| Equivalencia del crédito | precio de compra (spec 005) y `usage_records` de 30 días del partner | partner |
| Categorías de auditoría | `console_audit_vocabulary.category` | común |

Una migración de **datos**: `0129_console_audit_vocab_017`, que añade al
vocabulario las acciones nuevas (`console.capability.update`,
`console.agent.publish_from_bar`, `console.billing.email_update`) con sus
plantillas ES/EN y su categoría, y etiqueta ES/EN de cada categoría existente.

## Entidades expuestas por la API (nuevas o ampliadas)

### `ClientOut` (ficha) — amplía
- `sector: str | null` (R1, R5).
- `setup: {agent: bool, channel: bool, quota: bool, active: bool, next: "agent" | "channel" | "quota" | "activation" | null}` (R1.1, R1.3). `next` es el primer paso pendiente en ese orden; `null` cuando está atendiendo.
- `quota: {cap: int, remaining: int} | null` (R1.2).
- `health` se conserva íntegra (paridad con la 016).

### `ClientSummaryOut` (lista) — amplía
- `setup` (mismo objeto, sin `next`), `quota`, `conversations_7d: int` (R9.1). `out_of_quota` se conserva.

### `AgentBundleOut` — amplía
- `draft_screens: ("settings" | "capabilities" | "knowledge" | "prompt")[]` (R3.1): qué pantallas difieren entre borrador y activa; vacío sin borrador.

### `DraftDiffOut` — nueva (`GET …/agent/draft-diff`)
```
{ version: {draft: int, active: int | null},
  settings: [{field: "schedule" | "languages" | …, before: json, after: json}],
  capabilities: [{name, kind: "tool"|"skill", change: "enabled"|"disabled"|"mode", before, after}],
  knowledge: [{id, title, change: "added"|"removed"}],
  prompt: {before: str, after: str} }
```
Claves, no frases: la consola traduce.

### `CapabilityOut` — nueva (`GET …/capabilities`)
```
{ key: str,                 # nombre técnico (tool.name | skill.name)
  kind: "tool" | "skill",
  business_name: {es, en}, description: {es, en},
  function: "appointments" | "orders" | "messages" | "escalation" | "knowledge" | "other",
  sectors: [str],           # vacío = común a todos
  recommended: bool,        # la plantilla del sector la enciende
  enabled: bool, enabled_in_active: bool, usable: bool,
  connector: {slug, display_name, status} | null,
  mode: {default, override, effective} | null,   # solo herramientas; sin "needs_approval" en las opciones
  read_only: bool, destructive: bool,
  technical: {name, version, tags} }
```
Envoltorio: `{sector: str | null, has_draft, active_version, version, groups: [{function, items}], hidden_by_sector: int}`.

### `CapabilityUpdateIn` — nueva (`PUT …/capabilities`)
`{ key, kind, enabled?: bool, mode?: "always" | "never" }` — **un cambio por llamada** (R5.4). Respuesta: `CapabilityOut` + `draft_created`.

### `WalletOut` — amplía
- `equivalence: {usd_per_credit: float, credits_per_message: float, basis: "partner_30d" | "platform_default"}` (R6.2). Ausente si el saldo no se pudo leer.

### `AllocationOut` — amplía
- `client_name`, `out_of_quota` (ya en la 016), `consumed: int` (= `cap - remaining`) para la barra (R6.3).

### `AuditVocabularyOut` — amplía
- `categories: [{key, label}]` (R11.5). `GET /console/audit?category=`.

### `PlaygroundThreadOut`
- `title` deja de aceptar «Untitled» como valor por defecto: el servidor pone «Conversación del {fecha}» en el idioma del principal (R11.3).

### `BillingOut` / `BillingIn`
- `PUT /console/billing/email` (R11.5): `{billing_email}` con validación de correo y auditoría `console.billing.email_update`.

## Estados y transiciones

- **Puesta en marcha**: no es una máquina de estados nueva; es una lectura. El
  orden fijo `agent → channel → quota → activation` decide `next`.
- **Borrador**: sin cambios (existe / se publica / se descarta). Lo nuevo es
  la lectura por pantallas.
- **Capacidad**: `enabled` en borrador ↔ `enabled_in_active` en activa; el
  cambio de modo escribe `tool_modes` como hoy.

## Reglas de validación

- `CapabilityUpdateIn.mode` solo admite `always | never`; `needs_approval` →
  422 `mode_not_supported` (R5.7).
- `PUT /billing/email` exige un correo válido y no vacío; 422 `invalid_email`.
- `GET /console/audit?category=` con una categoría desconocida → 422.
- Nada de lo anterior acepta `tenant_id` ni `partner_id` en el body.
