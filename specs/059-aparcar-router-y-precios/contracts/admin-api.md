# Contrato: API de administración, spec 059

Todo va bajo `/admin` y exige el token de admin. Las escrituras exigen además
`X-Operator-Id` (`require_operator`) y un `reason` no vacío. Los errores siguen la
forma de siempre: `{"detail": {"code": "...", ...}}`.

## §1 `GET /admin/models/deployments` (existe; cambia la fila)

`DeploymentRow` gana tres campos. Los demás se quedan.

```jsonc
{
  "uses": {
    "defaults": ["respond", "respond_fallback", "companion"],   // usos del registro (research D1)
    "agents": 7,
    "clients": ["Amigable Cobro", "New Air Climatización"],
    "verified": true,
    "problem": null            // "no_heartbeat" | "unpublished" | "mismatch" cuando verified=false
  },
  "sale": {
    "state": "on_target",      // on_target | drift | below_floor | unweighted | per_minute | no_cost | unknown (sin objetivo legible)
    "lanes": {
      "input":      {"cost": "4.000000", "weight": "0.880000", "sale": "8.800000", "multiplier": "2.20"},
      "cache_read": {"cost": "0.400000", "weight": "0.088000", "sale": "0.880000", "multiplier": "2.20"},
      "output":     {"cost": "20.000000", "weight": "4.400000", "sale": "44.000000", "multiplier": "2.20"}
    },
    "proposed": {"input": "0.880000", "cache_read": "0.088000", "output": "4.400000"}
  },
  "retirement_blocked_agents": null   // un entero cuando status=retiring y retire_after <= now
}
```

La lista entera gana `sale_policy`:

```jsonc
{"multiplier": "2.2", "floor": "1.5", "sell_usd_per_million": "10"}
```

Si no se puede leer el ajuste, es `{"multiplier": null, ...}`, `sale.proposed` es
`null` y el estado es `unknown`, salvo que algún carril esté bajo el suelo
(requisito 4.7). El panel tolera una API anterior que no mande `uses`, `sale` ni
`sale_policy` (`normalizeList`): el uso queda sin verificar y la venta sin objetivo.

## §2 Retirar y «No disponible» (existen; nueva condición)

`POST /admin/models/deployments/{id}/retire` y `POST …/unavailable` responden
`409 model_in_use` si el modelo está en uso:

```jsonc
{"detail": {"code": "model_in_use", "defaults": ["respond", "respond_fallback"], "agents": 7, "clients": ["…"]}}
```

Responden `409 defaults_unverified` si no se pueden verificar los modelos que usa
el worker:

```jsonc
{"detail": {"code": "defaults_unverified", "problem": "unpublished"}}
```

En los dos casos el estado del modelo no cambia.

## §3 `POST /admin/models/deployments/{id}/prices` (existe; cambia)

- Responde `422 in_the_past` si `valid_from` es anterior a hoy (UTC).
- La respuesta deja de traer `alerts`. Ahora es `{"deployment": DeploymentRow}`.
- No emite ningún aviso a los partners.

## §4 `POST /admin/models/deployments/{id}/cancel-retirement` (nuevo)

Cuerpo: `{"reason": "..."}`. Lleva el modelo de `retiring` a `active`.

- `200 DeploymentRow`.
- `409 not_retiring` si el modelo no está en retirada.

## §5 `POST /admin/models/deployments/{id}/restore` (nuevo)

Cuerpo: `{"reason": "..."}`. Lleva el modelo de `unavailable` al estado que tenía
antes (data-model).

- `200 DeploymentRow`.
- `409 not_unavailable` si el modelo no está «No disponible».

## §6 `PUT /admin/models/deployments/{id}/weights` (nuevo)

Cuerpo: `{"input": "0.88", "cache_read": "0.088", "output": "4.4", "reason": "..."}`.
Los tres pesos son decimales mayores que 0. Errores:

| Código | Cuándo | Detalle |
|---|---|---|
| `422 partial_weights` | Falta alguno de los tres | |
| `422 below_floor` | Algún carril queda por debajo del suelo | `{"lanes": ["output"]}` |
| `422 per_minute` | El modelo no se cobra por tokens | |
| `422 reason_required` | Falta el motivo | |

Responde `200 DeploymentRow`. El cambio se audita y publica `CATALOG_CHANGED`.

## §7 `GET` y `PUT /admin/models/sale-policy` (nuevo)

`GET` devuelve el `sale_policy` de §1.

`PUT` recibe `{"multiplier": "2.5", "apply_to_all": true, "reason": "..."}`.

- `422 below_floor` si `multiplier` es menor que 1,5.
- Si va bien, devuelve `{"sale_policy": {...}, "applied_to": ["openai/gpt-5.6-sol", ...]}`.

Con `apply_to_all`, en la misma transacción, cada modelo cobrado por tokens que
tenga coste vigente recibe los pesos propuestos.

## §8 `GET /admin/whatsapp/login-beta/countries` (existe; cambia)

Antes devolvía `list[CountryOut]`. Ahora devuelve
`{"configured": bool, "countries": list[CountryOut]}`.

`configured` es verdadero si el despliegue tiene `meta_config_id_wa_login`.

## §9 `GET /admin/builder/judge-calibration` y `GET /admin/builder/eval` (existen; ganan campos)

- **Calibración del juez:** pasa de una lista a `{"judge_model": str,
  "judge_calibrated": bool, "reports": [...]}`. `judge_model` es el
  `default_models()["judge"]` de la API, y `judge_calibrated` se calcula sobre ese
  modelo.
- **Evaluación:** pasa de una lista a `{"bank_size": int, "runs": [...]}`.

## §10 Números de Auphere (existen; cambian el actor y el motivo)

`POST`, `PATCH` y `DELETE` exigen ahora `X-Operator-Id` (400 sin él). `PATCH` y
`DELETE` exigen además `reason`; el `DELETE` lo lleva en un cuerpo JSON. La auditoría
registra `operator:{email}` (`operator_actor`, como el resto de escrituras del panel)
y el motivo.

`PATCH` sigue aceptando `access_token` y `provider_phone_id`. El panel deja de enviar
`webhook_secret`, y la API lo sigue aceptando por compatibilidad.

## Lo que no cambia

`/admin/router/*` y `/admin/certifications/*` responden igual (requisito 2.8). Que
el panel deje de llamarlos no cambia su contrato.
