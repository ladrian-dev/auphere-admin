# Contrato: agentes y números (iteración 3)

## Consola del partner

Permisos: leer `agents:read`, escribir `agents:write`, números
`channels:write`. `{ref}` es el del cliente (opaco, 404 si no es del partner).
`{agent_id}` de otro cliente → 404.

| Método y ruta | Cuerpo | Respuesta |
|---|---|---|
| `GET /console/clients/{ref}/agents` | — | `[{id, name, status, is_principal, channels: [{id, display}], active_version, draft_version}]` |
| `POST /console/clients/{ref}/agents` | `{name, seed_template}` | agente con borrador v1 (con `stage_from_seed`) |
| `PATCH /console/clients/{ref}/agents/{agent_id}` | `{name?}` \| `{status: "archived"}` | agente · 409 `agent_has_channels` · 409 `last_agent` |
| `PATCH /console/clients/{ref}/channels/{channel_id}/agent` | `{agent_id}` | canal · 409 si el canal no es de rol agente |

Las rutas que hoy editan «el agente» aceptan `?agent=<agent_id>`; sin él,
actúan sobre el **agente principal** (el activo más antiguo), así que los
llamantes de hoy —incluido el Companion— siguen funcionando:

`/console/clients/{ref}/agent` (GET, `draft-diff`, `versions`, `publish`,
`rollback`, `from-seed`), `/agent/settings`, `/capabilities`,
`/playground/threads` (el hilo nuevo fija su agente).

**Lo que la implementación ajustó (2026-10-08):**

- `POST …/agents` lleva también `placeholders` (los obligatorios de la
  plantilla, como el alta de un cliente); 409 `name_taken`.
- `PATCH …/channels/{channel_id}/agent` responde 409 `channel_send_only`
  (número solo de envío: `config.agent_enabled = false`; el rol
  «notificaciones» no lo decide), 409 `agent_not_published` y 409
  `agent_archived`. Vive en `api/console/agents_list.py`.
- `GET …/playground/threads?agent=` lista solo los hilos de ese agente; los de
  antes de los agentes (sin agente) son del principal. Sin `?agent=`, todos.

## Admin

| Método y ruta | Notas |
|---|---|
| `GET /admin/tenants/{tenant_id}/agents` | lista como la de la consola |
| `POST /admin/tenants/{tenant_id}/agents` | `{name, seed_template?}` |
| `PATCH /admin/tenants/{tenant_id}/agents/{agent_id}` | renombrar / archivar con las mismas reglas |
| `…/agent-config…` | aceptan `?agent_id=`; sin él, el agente principal |

**Ajustes:** `POST …/agents` crea el agente **sin** versiones (`{name}`, con
`X-Operator-Id`); su primera versión se guarda con `PUT …/agent-config?agent_id=`
o `POST …/agent-config/from-seed?agent_id=`. Un `agent_id` que no es un agente
activo de ese cliente → 404 (y la clave `(tenant_id, agent_id)` de `0155` lo
impide en la base de datos). Promover y revertir van por número de versión, que
es único por cliente, así que no necesitan el agente.

## Runtime

- `promote` publica `nexus:agent_config:promote` con `"<tenant_id>:<agent_id>"`;
  el suscriptor invalida esa entrada y, para mensajes antiguos con solo
  `<tenant_id>`, todas las del tenant.
- El despachador resuelve `channel.agent_id` → versión activa del agente; un
  canal sin agente usa el principal.
