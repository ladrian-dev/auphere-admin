# Contrato: API de la consola — la agenda desde el agente

Rutas bajo `/console`, con el token EdDSA de 60 s de la consola. El cliente sale de `{ref}`
(`resolve_mapping` bajo el partner del principal); ningún cuerpo lleva `tenant_id` ni
`partner_id`. Un `ref` de otro partner da el 404 opaco de siempre. Ningún campo se llama como un
cuerpo de mensaje (`test_console_scope.py`, regla 3).

## 1. `GET /clients/{ref}/agents/draft-options` — cambia

`DraftOptionsOut` gana:

```jsonc
"agenda": {
  "offered": true,            // Reservas se ofrece a este cliente (hoy: tiene partner y no está archivado)
  "module_on": false,         // reservas_enabled
  "mode": null,               // "services" | "capacity" | null si está apagado
  "capacity_kind": null,
  "suggested_mode": "services",
  "suggested_kind": null      // en aforo, el tipo sugerido (restaurante → "restaurant")
}
```

`TemplateOptionOut` gana `"books": true | false` (la plantilla lleva `reservas.*`).

## 2. `POST /clients/{ref}/agents/draft-jobs` — cambia

`DraftJobIn` (sigue con `extra="forbid"`) gana:

```jsonc
{
  "name": "Recepción",
  "description": "…",
  "start": "describe",              // también "template" y "blank"
  "template_id": null,
  "agenda": true,                   // nuevo. null = como hasta hoy (lo que proponga el constructor; nunca enciende Reservas)
  "reservas": {                     // nuevo. Obligatorio si agenda=true y Reservas está apagado
    "mode": "services",             // "services" | "capacity"
    "capacity_kind": null           // obligatorio en "capacity" (los 6 de CAPACITY_KINDS)
  }
}
```

| Caso | Respuesta |
|---|---|
| `agenda=true`, módulo apagado, sin `reservas` | 422 `reservas_mode_required` |
| `reservas.mode="capacity"` sin tipo / con tipo en servicios | 422 `reservas_kind_required` / `reservas_kind_forbidden` |
| Encender falla (cliente archivado, sin partner) | 409 `archived` / `no_partner`. No hay trabajo ni agente |
| Correcto | Como hoy (202 con `job_id`, o 201 en plantilla y en blanco). Reservas ya está encendido cuando el trabajo empieza |

Permiso: `agents:write`. Auditoría: `client_access.updated` con `from_agent` si encendió.

## 3. `GET /clients/{ref}/agents/{agent_id}/agenda` — nueva

Permiso: `agents:read`.

```jsonc
{
  "offered": true,
  "module": { "on": true, "mode": "services", "capacity_kind": null },
  "ready": false,
  "missing": ["no_staff"],          // códigos de passing.NOT_READY_REASONS; vacío si está lista
  "draft": { "on": true, "tools_on": 9 },
  "published": { "on": false },
  "state": "prepared",              // "none" | "prepared" | "on"
  "structured": true,               // false: agente de instrucciones libres, sin propuesta
  "proposal": { "id": "…", "status": "open" } ,   // o null; status open | stale | applied | rejected | expired
  "job": { "id": "…", "status": "running" },      // o null: el trabajo de la propuesta en curso
  "suggested": { "mode": "services", "capacity_kind": null },
  "can_write": true,                // agents:write
  "max_tools": 60
}
```

## 4. `PUT /clients/{ref}/agents/{agent_id}/agenda` — nueva

Permiso: `agents:write`.

```jsonc
// entrada (extra="forbid")
{ "enabled": true, "reservas": { "mode": "services", "capacity_kind": null } }
```

- `enabled=true`: si el módulo está apagado, lo enciende (`turn_on_from_agent`); escribe las 9
  en el borrador (una validación, una escritura); en un agente estructurado encola `agenda_text`.
- `enabled=false`: quita las 9 del borrador y de `procedures[].tools`; nunca apaga el módulo ni
  toca reservas; en un agente estructurado encola `agenda_text` con la instrucción contraria.
- Repetir lo mismo no cambia las herramientas. Si no hay trabajo de la propuesta en curso
  ni propuesta abierta (falló, caducó, se aplicó o se descartó), la vuelve a pedir: es «Reintentar» y
  «Pedir la propuesta» de la consola. Como mucho hay un trabajo en cola por agente: el que espera lee el
  borrador al empezar, y la dirección (activar o quitar) sale del borrador, no de la petición.

Respuesta: la de §3 más `"proposal_reason": null | "build_budget_exhausted" | "not_structured"`.

| Caso | Respuesta |
|---|---|
| Módulo apagado y sin `reservas` | 422 `reservas_mode_required` |
| Pasa de 60 herramientas | 422 `{code: "too_many_tools", max: 60}`. No escribe nada |
| El AgentSpec resultante no valida | 422 `{code: "spec_invalid", problems}` |
| Sin presupuesto de construcción | 200: las herramientas cambian; `proposal_reason: "build_budget_exhausted"` |
| Otro partner | 404 opaco; nada escrito |

Auditoría: `console.agenda.update` y, si encendió, `client_access.updated`.

## 5. `GET /clients/{ref}/agents/{agent_id}/agenda/tools?lang=es|en` — nueva

Permiso: `agents:read`. La forma de `ConnectorToolsOut` (`agent_integrations.py:92-115`), para
reutilizar `ConnectorToolsDialog`:

```jsonc
{
  "slug": "reservas",
  "name": "Agenda (Reservas)",
  "permission": null,
  "tools": [
    { "name": "reservas.find_slots", "title": "Buscar huecos libres", "description": "…",
      "read_only": true, "enabled": true, "enabled_in_active": false,
      "locked": false, "locked_by": null, "needs_write_permission": false, "suggested": true }
  ]
}
```

Encender o apagar una sigue siendo `PUT /clients/{ref}/capabilities?agent=` (no cambia).

## 6. `GET /clients/{ref}/agents` — cambia

`AgentOut` gana `"agenda": "none" | "prepared" | "on"`.

## 7. `GET /clients/{ref}/agents/{agent_id}/draft` — cambia el cálculo, no la forma

`missing_capabilities` contrasta lo que guardó el constructor con lo que la versión tiene (R6).

## 8. `GET /clients/{ref}/agents/{agent_id}/proposals` — cambia

Cada operación de `diff.ops` lleva además `"before"`: el valor de ahora en ese puntero del borrador,
o `null` si no existía. Calculado al leer. Las operaciones de la propuesta de la agenda son de
primer nivel (`/procedures`, `/rules`, `/escalation`, `/skills`, `/instructions`, `/services`):
el antes y el después de cada bloque entero. Si la ficha dice que el equipo confirma las citas,
`diff.ficha_links = [{"section": "policies" | "faqs", "label": "Cancelación"}]`.

## 9. `GET /clients/{ref}/agents/{agent_id}/review` — cambia

- `no_hours` con un agente que reserva pasa de `block` a `warn`.
- Nuevo `agenda_not_ready` (`warn`), con `reasons` y el enlace a Reservas.
- Nuevo `forbids_agenda` (`warn`), con el puntero de cada texto y la acción de pedir la propuesta.
