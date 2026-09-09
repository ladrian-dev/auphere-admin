# Contrato — la API de consola del puesto de trabajo, a nivel de partner

Todo bajo `/console/workstation/*`, con sesión de persona, token EdDSA de 60 s y
`test_console_scope` cubriéndolo automáticamente. Los **ejecutables** no se mueven:
siguen en `/console/clients/{ref}/workstation/executables` (son del cliente).

## Permisos

| Permiso | Roles | Para qué |
|---|---|---|
| `workstation:read` | owner · admin · builder · analyst | ver máquinas y vínculos |
| `workstation:pair` | owner · admin · builder | **nuevo** — emparejar la propia máquina, vincular clientes, declarar |
| `workstation:write` | owner · admin | archivar cualquier máquina, ver todas (fija `app.workstation_manager`) |

Espejado en `apps/console/src/lib/permissions.ts`; el test de deriva lo vigila.

## Rutas

| Método y ruta | Permiso | Qué hace |
|---|---|---|
| `POST /pairing-codes` | pair | Emite el código (ver `pairing.md`) |
| `GET /devices` | read | Mis máquinas; con `write`, todas con `owner_display_name`. Campos: `id, display_name, hostname, platform, presence, last_heartbeat_at, enrolled_at, owner, clients[]` |
| `PATCH /devices/{id}` | pair (propia) / write | `{display_name}` |
| `DELETE /devices/{id}` | pair (propia) / write | Archiva con `revoked_reason = archivada_consola`. `404` si no es tuya y no eres gestor |
| `POST /devices/{id}/clients` | pair (propia) / write | `{client_ref}` → vínculo sin directorio. `404` si el cliente no es del partner |
| `DELETE /devices/{id}/clients/{ref}` | pair (propia) / write | Archiva el vínculo |
| `GET /setup` | pair | Los cuatro pasos de la puesta en marcha **de quien llama** (D10) |

`presence` ∈ `presente | ausente | nunca`; `clients[]` lleva
`{ref, name, workdir, needs_directory}`.

## Invariantes

1. Ninguna ruta acepta `partner_id`, `principal_id` ni `tenant_id`: salen de la
   sesión y de la RLS.
2. Ninguna ruta acepta un `workdir`: la consola **no** teclea rutas (R7.1).
3. Ninguna ruta añade ejecutables: eso es de Auphere (001-R5.4).
4. «Archivar» nunca borra; `DELETE` es el verbo HTTP, no el efecto.
