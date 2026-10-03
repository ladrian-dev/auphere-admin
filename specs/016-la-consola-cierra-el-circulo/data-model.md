# Modelo de datos: la consola cierra el círculo

Solo lo que cambia. Todo lo demás (canales, asignaciones, bindings de modelo,
credenciales, avisos) ya existe con su RLS; ver `nexus/architecture/console-map.md`.

## Sin migraciones de esquema

Ninguna tabla ni columna nueva. Una migración de **datos**: el vocabulario de
auditoría (`0128_console_audit_vocab_016`), que añade cuatro acciones con sus
plantillas ES/EN.

## Entidades tocadas

### `channels` (por tenant, RLS por `tenant_id`)
- Sin cambios de forma. Regla nueva de comportamiento: al conectar desde la consola, si `UNIQUE(type, provider_identifier)` salta, la API responde 409 `number_in_use` y no toca el otro tenant.
- Tras conectar, `tenants.status` pasa de `provisioning` a `active` si `partner.auto_activate` y hay agente activo (`activate_tenant_if_ready`), como ya hace la API de partners.

### `partner_allocations` (por partner, FORCE RLS por `app.partner_id`)
- Sin cambios de forma. Operación nueva `move(from_tenant, to_tenant, qty)`:
  - precondiciones: ambos tenants del partner, `from ≠ to`, `qty ≥ 1`, `qty ≤ from.cap`;
  - efecto: `from.cap −= qty`, `from.remaining = min(from.remaining, from.cap)`, `to.cap += qty`, `to.remaining += qty`; **una transacción**, filas bloqueadas en orden de `tenant_id`;
  - invariante: `Σ cap` antes = `Σ cap` después.

### Estado derivado `out_of_quota` (no se guarda)
- `out_of_quota(tenant) = wallet_ilegible ∨ sin_fila ∨ remaining ≤ 0` — la misma semántica que la puerta `allow_channel_turn`. Se calcula por lotes con sesión de partner y viaja en `health.missing` como `"quota"` (orden: `agent`, `whatsapp`, `quota`, `activation`).

### `console_notifications` (por partner)
- `kind` nuevo: `client.out_of_quota` (`severity=warning`, `payload={external_client_ref, remaining: 0}`, `dedupe_key=partner:{id}:client.out_of_quota:{ref}:{YYYY-MM-DD}`).
- `kind` nuevo: `client.model_reset` (`severity=info`, `payload={external_client_ref, from_model, to_model}`) cuando la allowlist deja fuera el modelo elegido.

### `tenant_model_bindings` (por tenant)
- Sin cambios de forma. Regla nueva: al reescribir la allowlist de un partner, se borran los bindings `respond` cuyo `model_id` ya no esté permitido.

### `tenants.agendapro_public_url` (por tenant)
- Sin cambios de forma. Pasa a poder escribirse desde la consola (`agents:write`), con auditoría `console.integration.agendapro_url`. Vacío = desenlazar.

### `tenant_connectors` (por tenant)
- Sin cambios de forma. La respuesta de la consola gana un bloque derivado `last_sync {status, added, deprecated, reason, at}` (calculado de la última sincronización, no persistido de forma nueva: `added/deprecated` salen de la sincronización recién hecha; `at` de `last_provider_synced_at`).

### `audit_log` (plataforma)
- Acciones nuevas: `console.allocation.move` (`{from, to, qty}`), `console.model.update` (`{model_id, previous}`), `console.integration.agendapro_url` (`{set: bool}`), `console.connector.connect` (`{slug, sync_status}`). Ninguna lleva credenciales ni tokens.

## Transiciones

```
Cliente:   provisioning ──(agente activo ∧ canal conectado desde consola ∧ auto_activate)──► active
Cupo:      con cupo ──(remaining llega a 0 / turno saltado)──► sin cupo ──(asignar o mover)──► con cupo
Aviso:     (turno saltado ∧ recomprobación = sin cupo ∧ sin aviso hoy) ──► client.out_of_quota
Conector:  disconnected ──(clave guardada)──► connected{last_sync: ok | error} ──(reintentar)──► connected{ok}
Modelo:    elegido ──(allowlist lo excluye)──► por defecto del plan + client.model_reset
```
