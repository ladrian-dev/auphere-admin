# Resumen de la noche del 2026-11-01: listo para grabar

Todo se hizo en **staging** (`develop`). Producción no se tocó y no se envió nada a revisión de Meta.

## Estado de cada canal (staging, cliente «Meta Review Demo», agente «Ava» v1)

| Canal | Recibe | Ava responde | Traspaso a persona | Persona responde | Comentarios |
|---|---|---|---|---|---|
| Instagram @somos.auphere | Sí | Sí, en inglés, en unos 5 s | Sí (`escalate`, `tool_calls=1`) | Sí, desde el panel | **No llegan**: Meta no envía el webhook `comments` (ver abajo) |
| Messenger (Página «Auphere») | Sí | Sí, en inglés | Sí | Sí | **Sí**: lectura del comentario, respuesta privada y respuesta pública |
| WhatsApp +34672138367 | Sí | Sí, solo al número de prueba del owner | Probado el 2026-10-31 | — | — |

## Lo que cambió esta noche

**Código** (todo en `develop`, desplegado en staging salvo el último, que tiene en marcha su CI):

| Commit | Qué |
|---|---|
| `4bfd7541` | Un comentario de la Página sin autor (`from`) se sigue atendiendo |
| `d9a0d101` | El aviso `feed` de Meta llega **sin el texto** del comentario: staging lo lee de Graph (`GET /{comment-id}?fields=message,from`, `pages_read_user_content`) antes de pasárselo a Ava; si Meta no lo da, se descarta con registro. El nombre de quien comenta sale del propio comentario |
| `efcbe391` | Prueba de la API que fallaba el día 1 de cada mes (el gasto caía en el mes anterior) |
| `94a0a2f0` | La pantalla «Estamos en la ventana de Meta» de Instagram y Messenger avisa de que el administrador debe dar acceso explícito a los activos del negocio. Lo pide la revisión de `business_management` y sale en el vídeo |

**Panel de Meta** (app `957213733862330`), con la autorización del owner:
- Webhook de Página: campo `feed` suscrito.
- `pages_read_engagement` en el caso de uso de Messenger. Meta lo añadió también al de Instagram.
- Caso de uso nuevo «Administrar todos los aspectos de tu página», con `pages_read_user_content` y `pages_manage_engagement`.
- Configuración «Auphere Messenger»: 7 permisos.
- Messenger reconectado en staging con los permisos nuevos. Ya tiene «Comentarios» con la línea pública «We sent you a private message 📩».

Todo esto queda en el **borrador de revisión**, sin enviar.

**Consola de staging:**
- Ficha del negocio: web `https://auphere.com`, cómo reservar la demo y cómo es el precio. Antes Ava decía a veces «I don't have a booking link».
- Conversaciones de prueba devueltas al agente después de cada traspaso.

**Llamadas con éxito para la regla de los 30 días:** `pages_read_user_content` (lectura del comentario) y `pages_manage_engagement` (respuesta pública) ya tienen la suya, del 2026-11-01 a las 03:19 UTC.

## Decisiones del owner

1. **Comentarios de Instagram.** El 2026-10-31 los comentarios no generaron webhook. La matriz oficial de Meta dice que `comments` con Facebook Login necesita también `pages_manage_metadata`, `pages_read_engagement` y `pages_show_list`, y la respuesta privada, `pages_messaging`. La configuración «Instagram API (Unified Login)» (`1157578836735566`) no los pide. Intenté añadirlos y el sistema de permisos lo bloqueó porque no estaba autorizado. **Propuesta:** añadirlos, reconectar Instagram y repetir el comentario.
   **Hecho el 2026-11-01:** con los 4 permisos y «Páginas» en la configuración, y tras reconectar, el comentario llega, Ava responde en privado y deja la línea pública «We sent you a private message 📩» (configurada ese día en el canal de Instagram). Si siguen sin llegar, se graba con la notificación de prueba del Dashboard, como explica `08` §4.
2. **Idioma de Ava.** No lo cambié. Ava tiene un borrador **v2** que creó el sistema el 2026-10-31 a las 19:14, al activar Reservas en el acceso del cliente. Tiene 14 habilidades (clínica estética, reservas…), frente a las 5 de la v1. Cambiar el idioma desde la consola publicaría ese borrador. La consola no tiene un botón para descartarlo (la API sí: `DELETE …/draft`). Ava ya responde en inglés a quien escribe en inglés. **Propuesta:** descartar la v2 y entonces poner el inglés como idioma principal.
   **Hecho el 2026-11-01:** la v2 se descartó. Se probó el inglés como idioma principal en una v3, pero Ava pasó a contestar en inglés a quien escribe en español (INC-55). Además, la puerta no la dejaba publicar por pruebas «Not sure» (INC-54). La v3 también se descartó. Ava sigue en la **v1**, que responde en inglés a quien escribe en inglés, y eso basta para los vídeos.
3. **`messaging_policy_enforcement`.** Lo pide la revisión de Messenger y el webhook de la Página no lo tiene suscrito. El 2026-10-30 el owner dijo «Ahora no». Cada Página sí lo pide en su suscripción.
4. **Human Agent.** El vídeo necesita una conversación cuya última respuesta del cliente tenga **más de 24 h**. La de Messenger con la cuenta del owner cumple 24 h desde su último DM el **2026-11-02 a las 00:29 UTC** y desde su último comentario a las **03:19 UTC** (04:19 en Madrid). Se graba el 2 de noviembre desde las 09:00, cuando staging despierta. (La hora de las 23:42 UTC que se dio antes contaba desde el primer mensaje y estaba mal.) No hay que escribir en ella hasta grabar ese vídeo.
5. **Canales abiertos.** Instagram y Messenger siguen en «A todos», y WhatsApp en «Solo mi equipo». En Instagram ha escrito al menos una persona ajena a las pruebas y Ava le contestó. Al terminar de grabar, pasarlos a «Sin configurar».
6. **WhatsApp +34672138367.** Siguen llegando a staging mensajes de personas ajenas a las pruebas. En coexistencia también les llegan a la app del teléfono.

## Comentarios de prueba que borrar (públicos)

En la publicación de la Página «Auphere» del 27 de octubre, con la cuenta «Andres Matos»:
- «Test: how much does it cost?» (00:32 UTC, se descartó antes del arreglo).
- «Test 2: do you work with dental clinics?» (03:19 UTC) y la respuesta de Auphere «We sent you a private message 📩».

En la publicación de Instagram «5 métricas que importan de un agente» de @somos.auphere (22 de septiembre), con la cuenta «andresmatos.ux», el 2026-11-01:
- «Test 3: do you offer a free trial?» (sin respuesta pública: aún no estaba configurada).
- «Test 4: can it book appointments?» y la respuesta de @somos.auphere «We sent you a private message 📩».

Los de la tarde del 31 los escribió el owner: «How much does it cost to?» en Instagram y «How much does it cost?» en Facebook.

## Para grabar

La guía completa está en `08-videos-revision-meta.md`. Lo esencial:
- **Un vídeo por permiso o función.** Empieza con la sesión cerrada, muestra Facebook Login for Business y la concesión del permiso, y después el uso del dato en la consola.
- **Formato:** 1080p o más, ventana de 1440 px de ancho o menos, todo en inglés (consola, Facebook, Instagram y el móvil), sin audio, cursor grande, rótulos y zoom.
- **Mensajería:** el vídeo tiene que mostrar el mensaje llegando a Instagram o Messenger; las capturas no valen. La respuesta automática, en menos de 30 s (hoy tarda unos 5 s).
- **Datos sensibles:** nada de tokens, del `code` de OAuth, de DevTools ni de teléfonos o datos de clientes reales.
- **Revisores:** entran con sus propias cuentas de Facebook. En el envío van credenciales de la consola, no de Facebook.
- **Antes de grabar, comprobar:**
  - que la app sigue publicada;
  - que la cuenta que escribe o comenta tiene rol en la app;
  - que hay una llamada con éxito de cada permiso en los últimos 30 días.
