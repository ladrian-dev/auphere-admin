# Iteración 1 — un número desvinculado no ocupa sitio

**Cerrada el 2026-09-29.** Se puede soltar sola: no toca Meta.

## Lo que cambió

| Antes | Después |
|---|---|
| `UNIQUE (type, provider_identifier)` — un número, una vez, para siempre | `UNIQUE INDEX … WHERE status <> 'disconnected'` — dos vivos no; uno vivo y uno desvinculado sí |
| B conectando un número que A soltó → `409 number_in_use` (falso) | → `201`, y la fila de A sigue, desvinculada, con su historial |

## Medido

| Qué | Resultado |
|---|---|
| T006 antes del índice | **rojo**: `{"detail":{"code":"number_in_use"}}` · 409 |
| T006 después | 201; la fila de A conserva id, tenant y `disconnected`; la de B es otra |
| T007 · reconectar en el mismo cliente | mismo `channel.id`; una sola fila con ese número |
| T008 · número vivo en A | 409 `number_in_use`; el cuerpo no nombra a A; A intacto |
| T004 · aislamiento | (a) B no ve ni choca con la fila desvinculada de A · (b) con A vivo, B choca contra `uq_channels_live_number` y A no cambia · (c) bajo el scope de B, el canal de A no existe: `rowcount == 0` · (d) 9 rutas de canal barridas por OpenAPI, ninguna acepta `tenant_id`/`partner_id` |
| T003 · medidor | `usage_events` igual antes y después de desvincular |
| T005 · `deregister_phone` | sin cuerpo, con `appsecret_proof`; un 400 de Meta sube como `MetaAPIError` |

## Suites

| Suite | Resultado |
|---|---|
| `test_endpoint_console_whatsapp` + `_channels` + `isolation/test_channel_number_scope` + `isolation/test_console_scope` | **593** ✅ |
| `apps/channels/tests/test_meta_client` | **19** ✅ |
| ruff check · format | limpios |
| Migración 0132 | aplicada en `nexus` y `nexus_test`; `\di channels` muestra `uq_channels_live_number` y ya no `uq_channels_type_provider_id` |

## Dos trampas del arnés, anotadas en el test para el siguiente

- Tras un `IntegrityError` dentro de `session.begin()`, la sesión queda rota:
  `rollback()` y releer **con consulta** — y capturar los ids **antes** del
  choque, porque el objeto expira y leerlo intenta IO síncrona.
- `session.get()` contesta desde la caché de identidad **sin ir a la base**, y
  la RLS vive en la base. Para probar aislamiento, `expunge_all()` y consulta.
