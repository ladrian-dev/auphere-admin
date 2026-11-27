# Investigación: el enlace para que el cliente conecte Instagram y Messenger

Base: el mapa del código del 2026-11-27 sobre `develop` `a5953d18`. Cada decisión cita lo que ya existe y lo reutiliza. La regla es la de Luis: el mismo flujo que WhatsApp, no uno distinto.

## R1. La tabla de enlaces admite los tres canales

- **Decisión:** la migración `0244` amplía `ck_channel_signup_links_channel` a `('whatsapp','instagram','messenger')`. `mode` sigue siendo obligatorio: los enlaces de Instagram y Messenger guardan `mode = 'meta_login'`, «el dueño entra a Meta». Una restricción nueva, `ck_channel_signup_links_mode_per_channel`, liga cada canal a sus modos: WhatsApp a sus tres modos de siempre, y Instagram y Messenger solo a `meta_login`.
- **Por qué:** la tabla ya tiene la columna `channel` (0160). No hace falta tabla nueva, y la forma de entrar a Instagram la elige el dueño (D1), así que no hay modo que fijar.
- **Descartado:** hacer `mode` nulo. Rompe la garantía de que cada enlace de WhatsApp lleva modo, y obligaría a tocar todo el código que lo lee.

## R2. Un enlace vivo por cliente y canal

- **Decisión:** `mint_link` recibe `channel`. Sin agente, solo anula los enlaces vivos del cliente **de ese canal**. `live_links` y `recent_links` devuelven el canal, y la lista del cliente lo muestra.
- **Por qué:** hoy anula todos los vivos del cliente (`channel_signup_links.py:105`). Un enlace de Instagram mataría uno de WhatsApp pendiente.

## R3. Un enlace pendiente por agente y canal, y los caducados no estorban

- **Decisión:** la migración `0244` cambia `uq_channel_signup_links_one_pending` a `(tenant_id, agent_id, channel)`. Además, `mint_link` con agente anula antes los enlaces del mismo agente y canal que estén caducados sin usar ni anular.
- **Por qué:**
  - El índice de hoy ignora el canal, así que un agente no podría tener a la vez pendientes un enlace de WhatsApp y otro de Instagram.
  - El índice tampoco excluye los caducados (un índice parcial no puede usar `now()`), y `mint_link` solo anula los vigentes. Un caducado sin anular hace fallar el `INSERT` siguiente con un 500. Es un fallo que ya existe y que se arregla aquí porque se toca esa misma lógica.
- **Consecuencia:** `agent_channels` devuelve `pending_links` (lista, uno por canal) además de `pending_link`. `pending_link` se queda para WhatsApp, así que no se rompe el contrato.

## R4. La elección pendiente sabe desde dónde se inició

- **Decisión:** `MetaSocialConnector.begin` y `complete` (`apps/channels/.../meta_social/connect.py`) reciben `origin: str`, que por defecto es `"console"`. Va dentro del JSON cifrado de la elección pendiente, y `complete` responde `pending_expired` si el origen no coincide. El enlace usa `origin = f"link:{link.id}"`.
- **Por qué:** hoy la elección pendiente solo va ligada al cliente y al `nonce` (`nexus:meta_social:pending:{tenant}:{nonce}`). Sin esto, una elección iniciada en la consola se podría completar desde un enlace, y al revés. Es el requisito 7.3 de la spec.
- **Descartado:** una clave de Redis aparte por enlace. Sería un segundo sitio que mantener, cuando el origen cabe en el mismo valor cifrado.
- **Nota:** la clave se borra antes del commit (`connect.py:203`). Si algo falla después, el dueño vuelve a empezar, y el enlace sigue valiendo porque solo se consume al conectar (requisito 5.5).

## R5. Disponibilidad por partner

- **Decisión:**
  - **La API:** las llamadas públicas cargan el partner por `tenant.partner_id` y aplican `meta_social_service.enabled_kinds(partner)`. Si el canal no está disponible, el enlace se trata como desconocido (404 `link_unknown`), sin explicar nada.
  - **La consola:** crear el enlace pide el mismo permiso y la misma disponibilidad que conectar desde la consola (`_require_enabled`).
- **Por qué:** la disponibilidad de hoy la decide `enabled_kinds`, y en producción está abierta a todos (`meta_social_general_availability`). La ausencia se diseña (§V): sin disponibilidad, la tarjeta no ofrece el enlace.

## R6. El canal llega al agente en el servidor

- **Decisión:** si el enlace trae `agent_id`, el servidor coloca el canal en ese agente con la **misma** función de servicio que usa la consola al mover un canal (`connect.move`), sin copiarla. Si esa función depende del `ClientScope`, se extrae la parte que trabaja con la sesión, sin cambiar su comportamiento en la consola. El alta se audita como `link:{id}`, con `channel.{kind}.connect`, y después del commit se avisa con `announce_connected`, igual que WhatsApp.
- **Por qué:** en la consola, colocar el canal lo decide el navegador (`placeSocial`). En la página pública no hay un partner que lo decida.

## R7. Lo que se devuelve al dueño

- **Decisión:** las respuestas públicas nuevas no devuelven `ChannelDetailOut`. Devuelven `status`, `nonce`, `accounts` (`id`, `name`, `username`, `picture_url`), `display_name` y `business_name`. Ningún campo se llama `reason`, `message`, `text`, `body`, `payload`, `content` ni `tenant_id`: `test_console_scope` los rechaza.

## R8. La página pública: una ruta para los dos canales, cookie por canal

- **Decisión:**
  - `link_url(token, channel)` da `/connect/{channel}/{token}`, así que WhatsApp no cambia.
  - En la consola, `app/connect/[kind]/` sirve `instagram` y `messenger`, y cualquier otro valor da `notFound`. `app/connect/[kind]/[token]/route.ts` guarda el token y redirige, como la de WhatsApp. La ruta estática `connect/whatsapp` tiene prioridad sobre `[kind]`.
  - La cookie es por canal: `nx_owner_link` para WhatsApp (sin cambios) y `nx_owner_link_instagram` y `nx_owner_link_messenger` para los demás. Así no chocan dos enlaces abiertos en el mismo navegador.
- **Por qué:** un solo componente y una sola ruta para Instagram y Messenger, sin duplicar por canal.

## R9. Un solo componente de conexión

- **Decisión:** `useMetaSocialConnect` recibe sus acciones inyectadas: `connect(kind, code)` y `complete(kind, nonce, accountId)`, y opcionalmente `onConnected` y `refresh`. Es el mismo patrón que `OwnerLinkPanel` (`actions?: OwnerLinkActions`).
  - La consola le pasa las acciones ligadas al `ref`, que son las de hoy.
  - La página pública le pasa las del enlace.
  - La pregunta «¿Cómo entras a Meta?», el diálogo de elegir y los motivos de error (`META_SOCIAL_REASONS`, `LOGIN_ERRORS`) son los mismos.
- **Textos:** se añaden `connect.social.*` (el título por canal, «¡Listo!» por canal, la explicación) y se reutilizan `ch.social.how.*`, `ch.social.choose.*`, `ch.social.reason.*` y `connect.dead.*`.
- **Descartado:** un hook nuevo para la página pública. Sería un segundo flujo.

## R10. El panel para compartir

- **Decisión:**
  - **El panel:** `whatsapp-share-link.tsx` pasa a ser un panel de enlace por canal. En WhatsApp conserva el selector de modo; en Instagram y Messenger no lo muestra. Copiar, enviar por WhatsApp, enviar por correo y la caducidad son los mismos.
  - **Dónde aparece:** el botón sale en las tarjetas de Instagram y Messenger de Canales del cliente. En el agente, `OwnerLinkPanel` recibe `channel`.
  - **La lista de pendientes:** `pending-signup-links.tsx` muestra el canal de cada enlace.
  - **La API de la consola:** `POST /console/clients/{ref}/channels/{kind}/signup-link`, con `kind` limitado a `instagram` o `messenger`, en `meta_social.py`, donde ya vive la conexión. En el agente, `OwnerLinkIn` gana `channel`, que por defecto es `whatsapp`.
- **Por qué:** hoy no se manda ningún correo desde el servidor. El texto para compartir sale de los textos de la consola (`ch.link.message`), así que basta con textos por canal.

## R11. La app móvil

- **Decisión:** no se regenera nada. `export_openapi.py` solo exporta `/console/lite` y `/app/`, y `lite.gen.ts` no toma `ch.link.`, `connect.`, `ch.social.` ni `builder.ownerLink.`. La única excepción: si se añaden textos bajo `builder.channel.state.*` o `builder.channel.problem.*`, hay que correr `pnpm --dir apps/mobile gen`. Se evita tocarlos.

## R12. Lo que queda fuera

- El panel de operador (`api/admin/channel_signup_links.py`): sigue solo con WhatsApp (spec, Fuera de alcance).
- El límite de 10 llamadas por minuto y token sobra: elegir cuenta son unas 3.
