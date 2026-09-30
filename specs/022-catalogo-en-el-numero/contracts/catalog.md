# Contrato — el catálogo del número

Todos bajo `/console/clients/{ref}/channels/{channel_id}`; permiso `channels:write`
salvo el GET de lectura, que basta con `channels:read`.

## `GET …/catalogs` — los catálogos del negocio

Lista los catálogos del negocio dueño del token del canal.

| Caso | Respuesta |
|---|---|
| ok | `200 {"items": [{"id","name","product_count"}], "linked_id": "…"|null}` |
| sin credencial | `409 {"code": "channel_has_no_credentials"}` |
| sin permiso de catálogo | `409 {"code": "catalog_permission_missing"}` |
| Meta caído | `503 {"code": "meta_unavailable"}` |
| canal de otro tenant | `404` (RLS) |

Nunca devuelve catálogos de otro negocio: solo los del token.

## `PUT …/catalog` — enlazar (o cambiar)

Body: `{"catalog_id": "…"}`.

| Caso | Qué hace | Respuesta |
|---|---|---|
| WABA sin catálogo | enlaza; guarda id y nombre | `200 ChannelDetailOut` |
| WABA con otro | desenlaza el viejo, enlaza el nuevo (D4) | `200`, `after.meta = {unlinked, linked}` |
| el nuevo falla tras desenlazar | el canal queda sin catálogo, con `catalog_error` | `200` con `catalog: null` y `catalog_error` |
| catálogo que no es del negocio | nada cambia | `409 {"code": "catalog_not_owned"}` |
| sin permiso | nada cambia | `409 {"code": "catalog_permission_missing"}` |

Auditoría: `console.channel.catalog` con `before/after`.

## `DELETE …/catalog` — desconectar

| Caso | Respuesta |
|---|---|
| ok | `200 ChannelDetailOut` con `catalog: null` |
| ya no tenía | `200`, sin llamar a Meta |
| Meta rechaza | `200` con `catalog` intacto y `catalog_error`; **no** se borra a ciegas |

## `ChannelDetailOut` — campos nuevos

```json
"catalog": {"id": "…", "name": "…", "checked_at": "…"} | null,
"catalog_state": "none" | "linked" | "permission_missing" | "unchecked",
"catalog_error": {"code": "…", "message": "…", "at": "…"} | null
```

`GET /console/clients/{ref}/channels` concilia con Meta (D3) antes de responder,
una vez por WABA cada 5 min; si Meta no responde, `catalog_state = "unchecked"`.

## Herramientas del agente (servidor interno `meta_catalog`)

| Herramienta | Entrada | Salida |
|---|---|---|
| `catalog.search_products` | `{query: str, limit?: int ≤ 10}` | `[{retailer_id, name, price, currency, availability, image_url}]` |
| `catalog.get_product` | `{retailer_id: str}` | uno de los anteriores, con `description` |

Ambas resuelven `catalog_id` y token del canal por el que llegó la
conversación; sin catálogo devuelven `catalog_not_linked` y el agente lo
dice como «no tengo catálogo para enseñarte». Nunca devuelven el token.
