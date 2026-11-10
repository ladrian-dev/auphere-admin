# Auditoría de la spec 049 contra la documentación oficial de Meta

Fecha: 2026-10-29. Se cruzan tres fuentes: la documentación oficial de Meta (`developers.facebook.com`, sobre todo las páginas nuevas `/documentation/`), el App Dashboard de la app `957213733862330` (leído en Chrome, sin cambiar nada) y el código de `develop` (`655b871e`).

## 1. Veredicto corto

- **La base es correcta.** Meta recomienda el inicio de sesión unificado para integraciones nuevas: no exige Página, va por `graph.facebook.com`, usa un token de usuario del sistema de integración (SUAT) que no caduca y los permisos de la familia `instagram_*`. Las configuraciones, los webhooks verificados y la decisión de no pedir `instagram_content_publish` siguen la documentación.
- **Código: no hay nada.** No existen parser, adapter, conexión ni migración. `/webhook/meta` responde 200 y descarta todo lo que no es `whatsapp_business_account` (`api/webhooks/meta.py:210`). `ChannelType` no tiene `messenger`.
- **Hay 7 desvíos que conviene corregir antes del plan** (§3). Dos de ellos bloquean la revisión: el revisor no tiene por dónde probar el flujo, y staging no puede recibir eventos de Instagram ni de Messenger.

## 2. Lo que está bien (verificado)

| Punto | Dashboard / spec | Documentación oficial |
|---|---|---|
| Vía de Instagram | Configuración «Instagram API (Unified Login)» `1157578836735566`, etiqueta «Compatible con el inicio de sesión de Instagram» | «Recommended setup for new integrations». El login con Instagram solo sale con configuraciones «Instagram Login Compatible» ([unified login](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/)) |
| Token | SUAT, caducidad «Nunca» | El SUAT pertenece al portfolio del cliente y por defecto no caduca. Exclusivo de Tech Providers y solo desde web ([FBL4B](https://developers.facebook.com/docs/facebook-login/facebook-login-for-business/)) |
| Permisos de Instagram | `instagram_basic`, `instagram_manage_messages`, `instagram_manage_comments` | Los dos primeros son obligatorios en Unified Login. Comentarios hace falta para las respuestas privadas |
| Fuera de alcance | Quitados `instagram_content_publish` y `ads_*` | Pedir permisos que no se usan es motivo de rechazo |
| Webhook único | `https://webhooks.auphere.com/webhook/meta` para `instagram`, `page` y `whatsapp_business_account` | Un callback por objeto y por app. Se puede repetir la URL y separar por el campo `object` |
| Firma | `verify_meta_signature` con `X-Hub-Signature-256` | HMAC-SHA256 con el app secret |
| App Live, `public_profile` Advanced | Publicada y aprobado el 2026-06-01 | Solo una app Live recibe eventos de terceros. FBL4B pide Advanced de `public_profile` |
| Negocio | Facelad verificado, Tech Provider | Se exigen Business Verification y Access Verification |
| Etiquetas de Messenger | Spec: solo agente humano | Desde el 27-abr-2026 la única etiqueta viva es `HUMAN_AGENT`; las otras tres devuelven error 100 |
| Regla de las llamadas | Kit: ≥ 1 llamada por permiso en 30 días | Oficial: «at least 1 successful API call… within 30 days». El contador tarda hasta 2 días ([submission guide](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/submission-guide)) |

## 3. Desvíos y huecos

### 3.1 Bloqueante: el revisor no tiene por dónde probar

La spec deja la conexión **solo en el panel de operador** (`admin.auphere.com`) y fuera de las consolas «hasta que Meta apruebe». Pero Meta revisa con sus propias cuentas y tiene que poder **conceder el permiso y usarlo** él mismo. Darle acceso al panel de operador le enseñaría todos los clientes. **Propuesta:** poner el flujo de conexión en la consola de partners, visible solo para un partner de revisión (módulo o flag por partner, spec 032), igual que el kit de catálogo.

### 3.2 Bloqueante para probar: staging no recibe eventos de Instagram ni de Messenger

WhatsApp separa entornos con `override_callback_uri` en cada WABA (`signup.py:193`). **Para `page` e `instagram` no existe override**: `POST /{page-id}/subscribed_apps` y `POST /{ig-id}/subscribed_apps` solo aceptan `subscribed_fields`. Todos los eventos van a la URL de producción. Hay dos salidas:

- **a) App de prueba de Meta para staging y local.** Meta la recomienda para desarrollo y QA. Es una app hija con su propio ID y secreto, siempre en modo desarrollo. Solo funciona con cuentas con rol, que es justo el caso de staging. Pide repetir allí las configuraciones y los webhooks.
- **b) Router en producción.** Si `entry[].id` no es de un canal de producción, reenviar a staging. Meta no lo documenta y acopla los entornos.

Recomiendo **a**.

### 3.3 La llamada de prueba de `instagram_basic` está mal

El kit dice `GET /me?fields=user_id,username` con el token del canal. Con un SUAT, `/me` devuelve el usuario del sistema, no la cuenta de Instagram. La forma documentada es:

1. `GET /me/assigned_instagram_accounts` para saber el `IG_ID`.
2. `GET /{IG_ID}?fields=username,profile_picture_url`.
3. `GET /me?fields=client_business_id` para guardar el negocio del cliente.

### 3.4 Messenger: la configuración y los webhooks no cumplen su lista de revisión

- La configuración «Auphere Messenger» `2188508105420190` pide `business_management`, `pages_manage_metadata`, `pages_messaging` y `pages_show_list`. **Falta `pages_read_engagement`**, que la documentación de Messenger exige y el kit pide (3.8). Sin él, el permiso no se puede demostrar en el login.
- La [lista de revisión de Messenger](https://developers.facebook.com/documentation/business-messaging/messenger-platform/app-review.md) pide además:
  - **suscribir `messaging_policy_enforcement`**, que hoy no está suscrito;
  - que la Página de prueba esté publicada;
  - que el webhook responda 200 en menos de 20 s;
  - que el tiempo medio de respuesta sea menor de 1 minuto.
- Si las entregas fallan durante 1 hora, Meta desuscribe la Página. La conexión tiene que detectarlo y volver a suscribirla.
- **Sin confirmar en la documentación:** cómo se pasa del SUAT al token de Página para `POST /{PAGE_ID}/messages`. La vía habitual es `GET /me/accounts` o `GET /{page-id}?fields=access_token` con el SUAT. Hay que probarlo con la Página de prueba antes de cerrar el plan.

### 3.5 Human Agent y traspaso en Instagram con Unified Login: sin confirmar

- La lista oficial de campos de webhook de Unified Login no incluye `messaging_handover` ni `standby`, aunque el Dashboard deja suscribir el primero (y está suscrito).
- La función Human Agent aparece en el caso de uso, pero la documentación de Unified Login no la nombra.
- La historia 4 depende de esto. Hay que probarlo en el spike: enviar con `tag=HUMAN_AGENT` desde una cuenta con rol.
- Si Meta usa el enrutamiento de conversaciones, la revisión pide ver que **la propiedad del hilo pasa a la bandeja** al escalar a una persona ([human agent escalation](https://developers.facebook.com/documentation/business-messaging/instagram-messaging/features/human-agent-escalation.md)).

### 3.6 Falta la función «Business Asset User Profile Access»

Sirve para leer el `name` y la `picture` de quien escribe (IGSID o PSID). El kit justifica el nombre del remitente con `pages_read_engagement`, pero ese dato lo da esta función, que también se revisa. **Hay que decidir:** pedirla y grabar su vídeo, o no mostrar nombres en la bandeja.

### 3.7 Reglas de Meta que la spec no recoge

| Regla oficial | Qué cambia en la spec |
|---|---|
| El cliente necesita un **portfolio de negocio**; Unified Login no admite usuarios de prueba | Caso límite nuevo: cuenta sin portfolio. Los activos de prueba son cuentas reales del equipo con rol de evaluador de Instagram (hoy hay 0 evaluadores) |
| El SUAT deja de valer si el cliente quita la app de su portfolio o mueve la cuenta a otro | Disparador de «requiere atención» y del plazo de borrado de 30 días (Req. 5.3) |
| Respuesta privada: `POST /{IG_ID}/messages` con `recipient.comment_id`, **una sola** por comentario y **dentro de 7 días**; luego solo si la persona contesta | Añadir el límite de 7 días al Req. 4.3 |
| Texto de DM de Instagram de **1000 bytes** como máximo; imágenes de 8 MB; audio, vídeo y PDF de 25 MB; sin grupos | Partir o recortar respuestas largas del agente |
| Reintentos de Meta durante **36 h** y lotes de hasta 1000 eventos | El dedupe en Redis de WhatsApp dura 5 min; para IG y Messenger hay que deduplicar por `mid` en Postgres |
| «Allow access to messages» apagado → error `(#200)` | Ya está en los casos límite; añadir el código de error |
| Ecos de Instagram: llegan en `messages` con `is_echo`, no hay campo `message_echoes` | Ya cubierto por el Req. 2.5 |
| Screencast: 1080p, inglés, **subtítulos o rótulos**, sin audio, botón de login visible y conforme a la guía de marca | Añadir al kit |
| Datos: instrucciones de borrado **o** callback con `signed_request` | Hoy apunta a la política de privacidad (vale). Un callback de borrado y desautorización es lo que hace cumplir el Req. 5.3 de forma automática |

## 4. Orden hasta el envío a revisión

1. **Decisiones del owner:** 3.1 (dónde se conecta el revisor), 3.2 (app de prueba o router), 3.6 (nombres en la bandeja) y si catálogo se envía antes o junto con Instagram y Messenger. Una solicitud en revisión bloquea la siguiente.
2. **Dashboard, cambios pequeños:**
   - Añadir `pages_read_engagement` a «Auphere Messenger».
   - Suscribir `messaging_policy_enforcement` en Page.
   - Dar rol de evaluador de Instagram y de Facebook a las cuentas de prueba.
   - Crear la app de prueba si se elige 3.2a.
3. **Spike de una tarde con cuentas con rol:** login unificado → `GET /oauth/access_token` → `assigned_instagram_accounts` → `subscribed_apps` → DM de ida y vuelta. Lo mismo con Página y `/{PAGE_ID}/messages`. Probar `HUMAN_AGENT`. Esto cierra los «sin confirmar» y ya cuenta como llamadas para el contador.
4. **Corregir la spec** con §3 y pasar a `/speckit-plan`.
5. **Construir:**
   - el parser compartido `object=instagram|page`;
   - los adapters, la migración de `messenger` y la conexión en la consola para el partner de revisión;
   - la ventana de 24 h / 7 días, comentarios y respuesta privada;
   - el traspaso a humano y el borrado a 30 días.
6. **Kit:**
   - Una llamada por permiso con más de 2 días de margen.
   - Un vídeo por permiso o función: `instagram_basic`, `instagram_manage_messages`, `instagram_manage_comments`, Human Agent, `pages_messaging`, `pages_manage_metadata`, `pages_show_list`, `pages_read_engagement` y `business_management`, más Business Asset User Profile Access si se pide.
   - Las instrucciones del revisor, reescritas.
7. **Enviar una sola vez.**

## 5. Fuentes principales

- Unified Login: https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/ y sus páginas `get-started`, `authentication`, `permissions`, `business-onboarding`, `eligibility-and-troubleshooting`, `migration`
- Webhooks de Instagram: https://developers.facebook.com/documentation/instagram-platform/webhooks/setup.md y `/webhooks/fields`
- Respuestas privadas: https://developers.facebook.com/documentation/instagram-platform/private-replies.md
- Messenger: https://developers.facebook.com/documentation/business-messaging/messenger-platform/overview.md, `send-messages.md`, `app-review.md`, `overview/rate-limiting.md`
- Facebook Login for Business: https://developers.facebook.com/docs/facebook-login/facebook-login-for-business/
- Override de WhatsApp (solo WABA): https://developers.facebook.com/docs/whatsapp/embedded-signup/webhooks/override
- Apps de prueba: https://developers.facebook.com/docs/development/build-and-test/test-apps
- App Review: https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/submission-guide y https://developers.facebook.com/documentation/instagram-platform/app-review.md
- Callback de borrado de datos: https://developers.facebook.com/docs/development/create-an-app/app-dashboard/data-deletion-callback
