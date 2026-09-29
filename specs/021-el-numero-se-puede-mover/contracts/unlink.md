# Contrato — desvincular, y conectar lo que otro soltó

## Desvincular (existe; cambia lo que hace)

```
POST /console/clients/{ref}/channels/{channel_id}/disconnect
```

| Estado del canal | Qué pasa |
|---|---|
| vivo | pasa a `disconnected` **antes de nada**; después se da de baja en Meta y, si era el último de su WABA en ese cliente, se desuscribe la app y se borran las credenciales |
| `disconnected` con `unlink_pending` | **reintenta** los pasos pendientes |
| `disconnected` sin pendientes | no hace nada; 200 |
| de otro tenant | 404 (RLS) |

**Respuesta**: el canal, con `unlink_pending` diciendo qué falta. Vacío es
«terminado del todo».

**Nunca** devuelve error por un fallo de Meta: el canal queda desvinculado en
la consola pase lo que pase, y lo que falló se lee en `unlink_pending`.

**Auditoría**: `console.channel.disconnect` con `after.meta = {done, pending}`.

**Permiso**: `channels:write`.

## Conectar (existe; cambia una respuesta)

```
POST /console/clients/{ref}/channels/whatsapp/signup
```

| Caso | Antes | Después |
|---|---|---|
| Número vivo en otro sitio | 409 `number_in_use` | igual |
| Número que otro desvinculó, y ya soltado en Meta | 409 `number_in_use` **(falso)** | 201: se conecta |
| Número que otro desvinculó, pero Meta lo retiene en su cuenta | mensaje genérico de Meta | 409 `number_held_by_previous_owner` |
| Número que **este mismo cliente** desvinculó | 201, reactiva su fila | igual, ahora con test |

**Nunca** dice de quién es un número en uso.
