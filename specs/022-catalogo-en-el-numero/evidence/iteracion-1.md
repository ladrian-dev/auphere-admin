# Iteración 1 — Meta, la API y la tarjeta (Historia 1)

**Cerrada en local el 2026-09-30.** Lo que solo se puede ver con Meta de
verdad (la lista real de catálogos, CE-002) espera al permiso
`catalog_management` en el panel de Meta (research D5).

## Lo que cambió el diseño al escribirlo

- **La conciliación se hace en `/overview`, no en un cron.** La tarjeta es el
  único sitio donde importa, y una llamada por cuenta cada 5 min es más
  barato que un cron que mire cuentas que nadie abre.
- **Cambiar = desenlazar + enlazar, y el fallo intermedio se dice.** Meta no
  garantiza que enlazar sustituya; el canal queda sin catálogo y con el
  motivo, en vez de fingir que el viejo sigue.
- **Sin credencial, desconectar no toca Meta y lo anota** (`skipped:
  no_credentials`), igual que desvincular en la 021.
- **El selector carga en un efecto sin escribir estado de forma síncrona**
  (el linter de React lo prohíbe) y olvida la lista al cerrar.

## Medido

| Caso | Resultado |
|---|---|
| Listar | los del negocio del token del canal, con `linked_id`; sin credencial 409 y **cero** llamadas a Meta |
| Permiso / caída | 409 `catalog_permission_missing` / 503 `meta_unavailable` |
| Enlazar | `id`+`name` en el canal; auditoría `console.channel.catalog` con `before/after` y `meta.linked` |
| Cambiar | `unlink` → `link`, en ese orden; `meta = {unlinked, linked}` |
| Segundo paso falla | `catalog = null`, `catalog_error.code = catalog_meta_rejected` con el texto de Meta |
| Ajeno | 409 `catalog_not_owned`, nada cambia |
| Desconectar | Meta `unlink`, claves borradas, caché de la cuenta invalidada; si Meta rechaza, el catálogo sigue y `catalog_error` lo dice |
| Conciliación | adopta lo de Meta · lo de Meta sustituye lo nuestro · caché 5 min · caída → `unchecked` sin borrar · permiso → estado · una cuenta = una llamada · sin credencial no pregunta |
| Permisos | analista lee (200) y no escribe (403) |
| Aislamiento | B no lista/enlaza/desconecta lo de A; Meta no se pregunta; la lista sale del token de A; rutas sin `tenant_id`/`partner_id`/`access_token` |
| Medidor | `usage_events` igual antes y después |
| Tarjeta (local, navegador) | «Catálogo · Flores y ramos · Cambiar · Desconectar» → selector con «Este número no tiene una conexión con Meta activa» (sin Meta local) → Desconectar con confirmación → `DELETE 200` → «Ninguno · Conectar catálogo» |

## Suites

| Suite | Resultado |
|---|---|
| `apps/channels` · `test_meta_client` | 24 ✅ |
| API · `test_endpoint_console_catalog` (17) + `isolation/test_channel_catalog_scope` (3) | 20 ✅ |
| API · canales + whatsapp + guarda de vocabulario + todo `isolation` | 1 210 ✅ |
| Consola · canales + catálogo + i18n | 100 ✅ · lint y `tsc` limpios |
