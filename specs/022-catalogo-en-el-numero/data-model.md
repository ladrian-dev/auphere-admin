# Modelo de datos — el catálogo en el número

## `channels.config` (JSONB) — claves nuevas

| Clave | Tipo | Quién la escribe | Cuándo se borra |
|---|---|---|---|
| `catalog_id` | `str` | enlazar (consola o Admin) · conciliación con Meta | desconectar · conciliación cuando Meta no lo tiene |
| `catalog_name` | `str` | enlazar · conciliación | con `catalog_id` |
| `catalog_checked_at` | ISO 8601 | conciliación | nunca; dice cuándo se comprobó por última vez |
| `catalog_error` | `{code, message, at}` | un rechazo de Meta al enlazar/desenlazar, o «no se pudo comprobar» | al siguiente éxito |
| `catalog_thumbnail_retailer_id` | `str` | ya existe (vía Admin); esta spec no lo toca | — |

Sin tabla nueva: el catálogo es un atributo del canal y la RLS lo alcanza por
`channels.tenant_id`. `business_id` ya está en `config` desde el alta; si un
canal viejo no lo tiene, se lee de la credencial del tenant.

## `console_audit_vocabulary` — migración `0134_audit_vocab_catalog` (26 caracteres)

| action | category | severity | summary_es |
|---|---|---|---|
| `console.channel.catalog` | `channels` | `info` | `{actor} cambió el catálogo de {client}.` |

`after_json`: `{"catalog": {"id","name"} | null, "meta": {"unlinked": id?, "linked": id?, "error": {...}?}}`.

## `tool_catalog` — migración `0135_catalog_tools` (20 caracteres)

| name | connector | default_mode | side_effects |
|---|---|---|---|
| `catalog.search_products` | nativa, `requires: channel_catalog` | `enabled` | ninguno |
| `catalog.get_product` | nativa, `requires: channel_catalog` | `enabled` | ninguno |

«Enviar productos del catálogo» es `response.send_interactive` con `products`:
no es una fila nueva; en Capacidades se enseña con nombre propio y `requires:
channel_catalog`.

## Caché (Redis)

`nexus:catalog:waba:{waba_id}` → `{"id","name"} | {"none": true}` · TTL 300 s.
Se invalida al enlazar o desenlazar desde la consola.

## Estados de la tarjeta

| Estado | Cuándo | Qué enseña |
|---|---|---|
| sin catálogo | `catalog_id` ausente y Meta tampoco tiene | «Catálogo: ninguno · Conectar» |
| con catálogo | `catalog_id` y Meta coinciden | «Catálogo: <nombre> · Cambiar · Desconectar» |
| sin permiso | Meta rechaza por permiso (D5) | frase de reconectar el número; sin botón de conectar |
| no comprobado | Meta no responde | lo guardado + «no se pudo comprobar hace N min» |
| solo lectura | quien no puede escribir canales | el nombre, sin controles |
