# Contrato — el código de emparejamiento y su canje

**El canal entre la consola y la cáscara es la persona.** La consola muestra un
código; la persona lo teclea en la barra; la barra lo canjea. Ninguna página le
habla al proceso principal (R3.5).

## Emitir — `POST /console/workstation/pairing-codes`

Permiso `workstation:pair` (owner · admin · builder). Sin cuerpo.

Respuesta `201`:

```json
{ "code": "K7MP-4XQ2", "expires_at": "2026-09-09T22:45:00Z", "ttl_seconds": 600 }
```

- El código se devuelve **una sola vez**; la base guarda su hash.
- Emitir otro código invalida los anteriores de la misma persona que no se hayan
  canjeado (un solo código vivo por persona).
- Auditoría: `device.pair_code_issued`, actor = la persona.

## Canjear — `POST /device/pair` *(sin credencial: el código lo es)*

```json
{ "code": "k7mp4xq2", "hostname": "MacBook-de-Luis.local", "platform": "macos", "app_version": "0.2.0" }
```

Normalización: mayúsculas, sin guion ni espacios; alfabeto
`ABCDEFGHJKMNPQRSTVWXYZ23456789`.

Respuesta `201` — **una sola vez**:

```json
{
  "device_id": "…", "credential": "<jwt>", "generation": 1, "expires_at": "…",
  "partner_slug": "nexus-retail", "principal_id": "…", "display_name": "MacBook de Luis"
}
```

Errores, **con el mismo cuerpo** para no distinguir (R3.3):

| Caso | Código | Cuerpo |
|---|---|---|
| No existe · caducado · ya usado · de otro partner | `404` | `{"code": "pairing_code_invalid"}` |
| Demasiados intentos | `429` + `Retry-After` | `{"code": "pairing_rate_limited"}` |
| Cuerpo mal formado | `422` | estándar |

Límite de intentos: 5 fallos por `hostname+IP` en 10 min → espera 60 s, que se
duplica en cada tramo hasta 15 min. Todo intento fallido se audita con su motivo
real (`device.pair_denied`), aunque al llamante no se le diga.

## Invariantes

1. El canje es **atómico**: `UPDATE … WHERE consumed_at IS NULL AND expires_at >
   now() RETURNING`. Dos canjes simultáneos: uno gana, el otro recibe `404`.
2. Partner y persona de la máquina salen **de la fila del código**, nunca del
   cuerpo.
3. Es la **única** ruta de `/device/*` que no exige credencial, y
   `test_device_bridge_inbound` la nombra como excepción documentada.
4. Sigue sin haber ninguna ruta que se dirija a una máquina por id, y el único
   `GET` sigue siendo el sondeo.
