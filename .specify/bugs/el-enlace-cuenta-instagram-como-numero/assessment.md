# Bug Assessment: el enlace de WhatsApp cuenta Instagram y Messenger como números

- **Slug**: el-enlace-cuenta-instagram-como-numero
- **Created**: 2026-11-27
- **Source**: texto pegado (Luis, clarificación de la spec 085, 2026-11-27)
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

> El enlace de WhatsApp (spec 040) cuenta las cuentas de Instagram y las Páginas de Messenger en la cuota de números del cliente (`partners.max_channels_per_client`). Un cliente con Instagram conectado y una plaza de número libre recibe «Este negocio ya tiene todos los números que puede conectar» al usar el enlace. La consola no los cuenta (spec 049) y además aplica la excepción de volver a autorizar un número que el cliente ya tiene (spec 076, 4.3). Decisión de Luis: arreglarlo aparte y ya, con la regla entera de la consola. Ya ocurre en producción.

## Symptom

Al usar un enlace de WhatsApp, un cliente con Instagram o Messenger conectados puede recibir `409 channel_quota_full` aunque tenga plazas de número libres. Lo esperado es la regla de la consola: solo cuentan los números de WhatsApp, y volver a autorizar un número que el cliente ya tiene no cuenta como otro.

## Reproduction

1. Un partner con `max_channels_per_client = 1`.
2. Un cliente suyo con un canal de Instagram conectado (`provider` de `META_SOCIAL_PROVIDERS`) y ningún número de WhatsApp.
3. El dueño completa un enlace de WhatsApp (`POST /console/channel-signup/{token}`): `connect_with_link` cuenta 1 canal, 1 ≥ 1, y responde 409 `channel_quota_full` antes de llamar a Meta.
4. Segundo caso: el cliente ya tiene su único número conectado, está en el tope y vuelve a autorizar **ese mismo** número por enlace. Responde 409, cuando la consola lo deja pasar (076, 4.3).

## Suspected Code Paths

- `apps/api/src/nexus_api/services/channel_signup_links.py:261-290` (`connect_with_link`): repite el recuento con solo `status != DISCONNECTED` y `provider not in _INTERNAL_PROVIDERS`. No excluye `META_SOCIAL_PROVIDERS` y no tiene la excepción de volver a autorizar.
- `apps/api/src/nexus_api/api/console/channels.py:249-263` (`count_connected_channels`): la regla de la consola, que excluye `INTERNAL_PROVIDERS` y `META_SOCIAL_PROVIDERS` (spec 049).
- `apps/api/src/nexus_api/api/console/whatsapp.py:84-95` y `231-245` (`_is_reconnect`): la excepción de 076, 4.3. Recibe un `ClientScope`, así que el enlace no puede usarla tal cual.
- `apps/api/src/nexus_api/api/console/channels.py:303-307` (`channels_overview`): una tercera copia del recuento, la que pinta la consola. Usa la misma exclusión de Instagram y Messenger.

## Root Cause Hypothesis

La spec 049 cambió la regla de la cuota en la consola (`count_connected_channels`) para no contar Instagram ni Messenger. El enlace de la spec 040 tenía su propia copia del recuento y no se actualizó. La excepción de la 076 (4.3) también se añadió solo en el camino de la consola. Confianza: alta. Está leído en el código, y ninguna prueba cubre `channel_quota_full` en el enlace.

## Proposed Remediation

**Preferred**: la regla vive en un solo sitio y la usan los dos caminos.
- Se mueve `count_connected_channels(session)` a un módulo de servicio (`services/channel_quota.py`), junto con `is_reconnect(session, phone_number_id)`. Esta función es la de `_is_reconnect`, pero recibe la sesión en vez del `ClientScope`.
- `api/console/channels.py` reexporta `count_connected_channels` (su `__all__` la publica) y `whatsapp.py` usa las dos funciones del servicio.
- `connect_with_link` llama a `count_connected_channels(session)` y deja pasar el caso de volver a autorizar con `is_reconnect(session, payload.phone_number_id)`.
- El mensaje y el código de error del enlace (`channel_quota_full`) no cambian.

**Alternatives**:
- Importar `count_connected_channels` desde `api.console.channels` dentro del servicio, y copiar `_is_reconnect` adaptada a la sesión. Hay precedentes de servicios que importan de `api.console`, pero la excepción quedaría duplicada y la regla en dos sitios otra vez.
- Que `channels_overview` use también la función común: es visualización, y queda como mejora si el cambio es trivial.

**Files likely to change**:
- `apps/api/src/nexus_api/services/channel_quota.py` (nuevo)
- `apps/api/src/nexus_api/services/channel_signup_links.py`
- `apps/api/src/nexus_api/api/console/channels.py`
- `apps/api/src/nexus_api/api/console/whatsapp.py`
- `apps/api/tests/integration/test_channel_signup_links.py`

**Tests to add or update** (en `test_channel_signup_links.py`, en rojo antes del arreglo):
- Un cliente con Instagram conectado y un tope de 1 conecta un número por enlace.
- Un cliente en el tope que vuelve a autorizar su mismo número por enlace no recibe 409.
- Un cliente en el tope con un número distinto sigue recibiendo `channel_quota_full`, para que el arreglo no abra la cuota.

## Risks & Considerations

- **Aislamiento:** el recuento y la búsqueda del número corren con la sesión del enlace, ya acotada al cliente (`tenant_scoped_session`). Las funciones nuevas no aceptan `tenant_id` y leen bajo la RLS. No se toca ninguna garantía.
- **Sin migración ni cambio de contrato:** solo cambia cuándo responde 409.
- **«WhatsApp login»:** su `phone_number_id` puede no venir en el payload. En ese caso `is_reconnect` devuelve `False` y la regla es la de siempre.
- **La consola no cambia de comportamiento:** solo cambia de dónde importa las funciones.

## Open Questions

- Ninguna: Luis decidió el alcance el 2026-11-27, con la regla entera de la consola.
