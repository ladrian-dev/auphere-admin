# Contrato — el puente, versión 2: las cinco operaciones de la credencial

Sustituye a `specs/001-puesto-trabajo-partner/contracts/device-bridge.md` en lo
que toca a la credencial y añade dos operaciones. Sigue siendo **saliente**: todo
es respuesta a una llamada de la máquina.

## La credencial

JWT HS256, TTL 12 h. Claims: `svc="device"` · `sub=device_id` · `pid=partner_id`
· `gen` · `iat` · `exp` · `iss` · `aud`. **No lleva tenant**: el tenant lo fija
cada trabajo y cada vínculo, por `client_ref` resuelto dentro del partner.

`require_device` — en cada petición, en este orden:

1. Firma, `iss`, `aud`, `exp`, `svc` → si falla, `401` sin motivo.
2. Carga la fila `partner_devices` por `sub` (rol dueño, clave primaria).
3. `revoked_at IS NOT NULL` → `403 {"code": "device_archived", "reason": <revoked_reason>}`.
4. `gen` ≠ `credential_generation` y no está en la gracia (`gen == generation − 1`
   y `now − credential_rotated_at ≤ 60 s`) → `401`.
5. `last_heartbeat_at < now − 30 d` → `403 {"code": "pairing_required"}`.
6. Fija `app.partner_id` y `app.principal_id`, baja a `nexus_app`.

## Las cinco operaciones — y ninguna más

| Operación | Ruta | Cuerpo | Efecto |
|---|---|---|---|
| **Latir** | `POST /device/heartbeat` | `{app_version?}` | **Solo** mueve `last_heartbeat_at` (invariante de `T072`) |
| **Sondear** | `GET /device/poll` | — | Devuelve `work[]` y **`links[]`**: `{client_ref, client_name, workdir, needs_directory}` |
| **Devolver resultado** | `POST /device/result` | como en v1 | Cierra el asiento de ejecución |
| **Renovar** | `POST /device/renew` | — | `gen + 1`, `credential_rotated_at = now()`. Respuesta `{credential, generation, expires_at}`. Audita `device.renewed`, actor `device:{id}` |
| **Declarar directorio** | `POST /device/links` | `{client_ref, workdir, checks: {exists, is_dir, resolves_within, readable}}` | Resuelve `client_ref` por `partner_tenants` bajo el partner de la firma; `404` si no es suyo (y se audita); escribe `workdir`, `declared_at` en el vínculo bajo `app.tenant_id` |

`checks` viaja para la auditoría: la máquina afirma qué validó (R7.2). La
plataforma no confía en ello para nada más — vuelve a validar al usarse
(001-R1.4).

## Qué hace la máquina con cada rechazo

| Respuesta | Estado de la barra | Puente |
|---|---|---|
| `401` | `hay que volver a emparejar` | para; olvida la credencial |
| `403 device_archived` | `archivada desde la consola` | para; olvida la credencial |
| `403 pairing_required` | `hay que volver a emparejar` | para; olvida la credencial |
| red / 5xx | `reconectando` | reintenta con retroceso, como en v1 |

## Invariantes

1. Sin conexiones entrantes, sin `{device_id}` en ninguna ruta, un solo `GET`.
2. El tenant nunca llega del llamante: `client_ref` es un nombre que la plataforma
   resuelve dentro del partner de la firma.
3. Ninguna de las cinco operaciones debita nada (R9.2).
4. La credencial se guarda en la máquina cifrada con `safeStorage`, por persona.
