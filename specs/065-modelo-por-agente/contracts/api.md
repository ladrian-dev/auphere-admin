# Contratos: El modelo de cada agente

**Spec**: [spec.md](spec.md) · Dinero en cien milésimas de la moneda de la cuenta (`amount_micros`, USD), como el resto del contrato de la consola.

## Consola de partners

### `GET /console/clients/{ref}/agents/{agent_id}/model` · `agents:read`

```json
{
  "agent_id": "uuid",
  "choice": { "model_id": "openai/gpt-5.6-terra", "display_name": "Terra", "set_by": "partner", "set_at": "2026-11-20T10:00:00Z" },
  "effective": { "model_id": "openai/gpt-5.6-terra", "display_name": "Terra", "source": "agent", "outside_offer": null,
                 "estimate": { "amount_micros": 6269, "currency": "USD", "basis": "agent_7d" } },
  "options": [
    {
      "model_id": "openai/gpt-5.6-luna",
      "display_name": "Luna",
      "provider": "openai",
      "line": "economy",
      "estimate": { "amount_micros": 550, "currency": "USD", "basis": "agent_7d" }
    }
  ],
  "notice": null,
  "can_change": true
}
```

- `choice` es `null` cuando el agente sigue el modelo por defecto de Auphere. La consola no lo distingue en pantalla (requisito 2.7): marca `effective` como «Ahora».
- `effective.estimate` lleva el precio del modelo con el que responde, también cuando no está en `options`.
- `effective.outside_offer` ∈ `null` · `retired` (ya no se ofrece, 12.5) · `operator` (lo eligió Auphere fuera de la lista del partner, 7.3): la consola lo dice en una línea con su precio.
- `effective.source` ∈ `agent` · `agent_operator` · `version` · `platform`.
- `options` es la oferta del partner (activo ∩ habilitado para responder en este entorno ∩ con perfil de llamada ∩ lista del partner), de menor a mayor precio. Si el agente tiene un modelo elegido por Auphere fuera de la oferta, `choice` lo enseña y `options` no lo incluye.
- `line` ∈ `max` · `balanced` · `economy`: la consola lo traduce a «Para agentes con muchas herramientas o casos difíciles», «Para la mayoría de agentes de atención y reservas» y «Para preguntas frecuentes y respuestas cortas» (requisito 1.5).
- `estimate.basis` ∈ `agent_7d` (consumo real del agente) · `nominal` (sin consumo).
- Los modelos que no pueden ejecutar lo que usa el agente (Skills o conector MCP de Anthropic) no aparecen en `options` (requisito 4.8; Principio V).
- `notice` ∈ `null` · `chosen_model_cannot_run_agent`: el modelo elegido dejó de poder ejecutar lo que usa el agente y el turno responde con `effective`, que en ese caso no es la elección.
- `can_change` refleja `agents:write`.
- Un agente de otro cliente, archivado o inexistente: `404`, el mismo para los tres (requisito 10.2).

### `PUT /console/clients/{ref}/agents/{agent_id}/model` · `agents:write`

Cuerpo: `{"model_id": "openai/gpt-5.6-luna"}` o `{"model_id": null}` (volver al modelo por defecto; la API lo acepta, pero la consola no lo ofrece, requisito 2.7). `extra="forbid"`.

- `200` con la misma forma que el `GET`.
- `422 {"code": "unknown_model", "model_id": …}` si no está en la oferta del partner, no tiene perfil o no está activo.
- `422 {"code": "model_unavailable_for_agent"}` si el agente usa algo que ese modelo no ejecuta.
- Efecto: escribe las tres columnas de `agents` con `set_by = 'partner'`, deja `console.agent.model.update` en la auditoría y publica `"{tenant_id}:{agent_id}"` en el canal de promoción (invalida solo ese agente).
- No lanza pruebas ni publica versión (requisito 6.2).

### `GET /console/models` (ya existe)

Gana `provider` y `line` en cada elemento, y solo lista modelos con perfil de llamada. El resto no cambia.

### Se retira

`PUT /console/clients/{ref}/model` responde `410 {"code": "client_model_retired"}` y `GET /console/clients/{ref}/model` desaparece (requisito 12.4). El copiloto ya propone por agente (requisito 2.9) y la pantalla de la consola antigua se retira (9.3).

## Panel de operador

### `GET /admin/tenants/{tenant_id}/agents/models` · token de operador

```json
[
  { "agent_id": "uuid", "name": "Recepción", "lifecycle": "active",
    "choice": { "model_id": "…", "display_name": "…", "set_by": "operator", "set_at": "…" },
    "effective": { "model_id": "…", "display_name": "…", "source": "agent_operator" } }
]
```

### `PUT /admin/tenants/{tenant_id}/agents/{agent_id}/model` · token de operador

Cuerpo: `{"model_id": "…" | null, "reason": "texto"}`. Acepta cualquier modelo activo, con perfil y habilitado para responder en el entorno, esté o no en la lista del partner (requisito 7.2). Escribe con `set_by = 'operator'`, audita `admin.agent.model.update` con el motivo y publica la invalidación del agente.

### `POST /admin/models/deployments/{deployment_id}/respond-enable` y `/respond-disable` · token de operador

Con la convención de las demás acciones del catálogo (`…/retire`, `…/unavailable`); `{deployment_id}` es el `uuid` de cada fila de `GET /admin/models/deployments`. Las dos devuelven la fila actualizada.

- `respond-enable`, cuerpo `{"note": "pasada de la batería: fecha, commit, resultado"}`:
  - `409 {"code": "no_respond_profile"}` si el modelo no tiene perfil de llamada;
  - `422` si falta la nota o el modelo no está activo;
  - escribe `respond_enabled_*`, audita `admin.model.respond_enable` y publica `CATALOG_CHANGED`.
- `respond-disable`, cuerpo `{"reason": "…"}`:
  - pasa al modelo por defecto las elecciones de agentes hechas por partners con ese modelo, con `agent.model_reset` (requisito 1.4);
  - `409 {"code": "model_in_use", "uses": ["agent_default" | "respond_fallback_openai" | "respond_fallback_anthropic"]}` si es el valor por defecto o la reserva habilitada de la otra familia;
  - audita `admin.model.respond_disable`.
- `GET /admin/models/deployments` (lista del panel) gana, en cada fila, `respond_enabled_at`, `respond_enabled_by`, `respond_enabled_note` y `has_respond_profile`.

### `GET/PUT /admin/platform/agent-respond-default` · token de operador

- `GET`: `{"model_id", "display_name", "set_by", "set_at"}` y las opciones (modelos habilitados).
- `PUT`, cuerpo `{"model_id", "reason", "confirm": false}`:
  - sin `confirm`, `409 {"code": "confirm_required", "affected": [{"tenant_id", "external_client_ref", "agent_id", "agent_name", "current_model"}]}`;
  - con `confirm: true`, escribe el ajuste, audita `admin.platform.agent_respond_default` con el motivo, invalida los agentes afectados y les devuelve la pasada de pruebas (requisito 13.5);
  - `422 unknown_model` si no está habilitado para responder.

### Cambios en lo que ya existe

- `PUT` y `DELETE /admin/tenants/{tenant_id}/model-bindings/respond`: `422 {"code": "respond_is_per_agent"}`. Los demás roles no cambian (requisito 12.4).
- `GET /admin/models` y la edición de pesos (spec 059): ganan `quota_weight_cache_write`.

- `PUT /admin/partners/{partner_id}/models`: valida contra los modelos **ofrecibles** (`offer_label`, activos y con perfil), no contra los habilitados, para poder poner los de Anthropic en la lista antes de habilitarlos. Tras reescribir la lista, además de `reconcile_bindings`, pasa al modelo por defecto los agentes con `set_by = 'partner'` cuyo modelo ya no está permitido, y emite `agent.model_reset` por agente (requisito 8.2). No toca elecciones de Auphere (8.3).
- `POST /admin/models/{id}/retire` y `/unavailable`: `409 model_in_use` también cuando un agente no archivado lo tiene elegido, con la lista de agentes (requisito 8.1).

## Lo que informa el turno

- Evento `llm.call_complete` (ya existe): sin cambios; ya lleva el `model` real de cada llamada.
- Evento nuevo `llm.respond_fell_back` (warning): `tenant_id`, `agent_id`, `chosen`, `served`, `reason` (`error` · `timeout` · `refusal` · `rate_limit`, de la clase original del último error antes de la reserva). Sin texto.
- `handler.turn_complete` y el estado del turno: `respond_model` / `response_model` = el modelo que respondió; `fell_back: bool`.
- Resultado de cada prueba de la batería y respuesta del Playground del agente: `model` y `fell_back`.
