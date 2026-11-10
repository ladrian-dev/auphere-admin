# Permisos de Meta: uso real, evidencia y estado

Fecha: 2026-10-30. App de Meta `957213733862330` (la misma para staging y producción).

## Cómo leer esta tabla

- **Estado en Meta** sale de la lectura del Dashboard del 2026-10-29 (memoria del proyecto y `specs/049…/auditoria-docs-oficiales.md`). Hoy no se ha vuelto a leer el Dashboard.
- **Requisito oficial verificado hoy**: solo lo que he contrastado hoy en `developers.facebook.com`. El resto se marca «según auditoría 2026-10-29», que cita fuentes oficiales pero no se ha vuelto a comprobar.
- **Preparación**: `Listo` (hay evidencia E2E), `Código listo, sin E2E` (solo inspección y tests con mocks) o `Bloqueado` (falta algo para poder grabar).

## Discrepancia en la documentación

`kb/Auphere/nexus/whatsapp-connector/meta-app-ids.md` (actualizado el 2026-05-21) dice que `business_management` tiene acceso avanzado aprobado. La lectura del Dashboard del 2026-10-29 dice que solo están aprobados `whatsapp_business_messaging`, `whatsapp_business_management` y `public_profile`, y que `business_management` está en el borrador sin enviar. **Lo que cuenta es el Dashboard.** Conviene corregir la KB (ver INC-12).

## Matriz

| Canal | Permiso o función | Uso real en el producto (código) | Estado en Meta | Requisito oficial | Caso que lo valida | Escena | Preparación |
|---|---|---|---|---|---|---|---|
| WhatsApp | `whatsapp_business_management` | Embedded Signup, alta del número, plantillas, salud de la cuenta, suscripción de la WABA (`api/console/channel_signup.py`, `whatsapp_health_cron.py`) | Aprobado (2026-06-01) | Meta revisa de nuevo el acceso existente con cada envío (según auditoría 2026-10-29) | WA-01…WA-06 | V-WA-1 | Código listo, sin E2E en staging (no hay ningún número conectado en el partner de staging) |
| WhatsApp | `whatsapp_business_messaging` | Envío y recepción por Cloud API (`/{phone_number_id}/messages`, webhook `whatsapp_business_account`) | Aprobado | Igual | WA-07, WA-08 | V-WA-1 | Igual |
| Catálogo (WhatsApp) | `catalog_management` | `GET /{business}/owned_product_catalogs`, `GET/POST /{waba}/product_catalogs`, `GET /{catalog}/products` (agente) | En borrador, sin enviar. Acceso estándar: solo funciona con cuentas con rol en la app | **Verificado hoy:** la referencia de `/{waba}/product_catalogs` dice que DELETE no se puede hacer en ese edge ([referencia Graph](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account/product_catalogs/)) | CAT-01…CAT-08 | V-CAT-1 | **Bloqueado**: INC-01 (desconectar/cambiar llama a un DELETE que Meta no tiene) e INC-02 (el cliente de demo en coexistencia no deja ver la lista) |
| Catálogo / Messenger | `business_management` | Listar los catálogos del portfolio del cliente (`owned_product_catalogs`). En Messenger está en la configuración de login | En borrador, sin enviar | Según auditoría 2026-10-29 | CAT-02 | V-CAT-1 (paso de la lista) | **Bloqueado** por lo mismo que la fila anterior: en coexistencia la lista no aparece |
| Instagram | `instagram_basic` | Cuenta conectada: `GET /me/assigned_instagram_accounts` + `GET /{IG_ID}?fields=username,profile_picture_url` | Sin aprobar ni enviar | Obligatorio en el login unificado (según auditoría 2026-10-29) | IG-01…IG-04 | V-IG-1 | **Bloqueado**: Instagram sale «Próximamente» en staging (partner sin `beta_channels`) y staging no recibe eventos de Instagram (INC-03) |
| Instagram | `instagram_manage_messages` | DM entrante por webhook (`object=instagram`) y respuesta `POST /{IG_ID}/messages` | Sin aprobar ni enviar | Igual | IG-05, IG-06 | V-IG-2 | Bloqueado (igual) |
| Instagram | `instagram_manage_comments` | Respuesta pública `POST /{comment-id}/replies` y respuesta privada con `recipient.comment_id` (una por comentario, dentro de 7 días) | Sin aprobar ni enviar | Según auditoría 2026-10-29 (respuestas privadas) | IG-07 | V-IG-3 | Bloqueado (igual) |
| Instagram, Messenger | Función Human Agent (`HUMAN_AGENT`) | Una persona del equipo responde entre 24 h y 7 días (`services/meta_window.py`) | Sin pedir | En Messenger es la única etiqueta viva desde el 27-abr-2026. En Instagram con login unificado está **sin confirmar** (según auditoría 2026-10-29) | IG-08, MS-06 | V-HA-1 | Bloqueado, y con un riesgo de producto: confirmar que funciona con login unificado antes de grabar |
| Instagram, Messenger | Business Asset User Profile Access | Nombre y foto de quien escribe (`GET /{IGSID}`, `GET /{PSID}`) | Sin pedir | Según auditoría 2026-10-29. **Decisión pendiente del owner:** pedirla o no mostrar nombres | IG-09, MS-07 | V-PROF-1 | Pendiente de decisión |
| Messenger | `pages_show_list` | Lista de Páginas en el login | Sin aprobar ni enviar | Según auditoría 2026-10-29 | MS-01, MS-02 | V-MS-1 | Bloqueado (igual que Instagram) |
| Messenger | `pages_manage_metadata` | `POST/DELETE /{page-id}/subscribed_apps` al conectar o desconectar, y resuscripción en el cron | Sin aprobar ni enviar | Igual | MS-03, MS-08 | V-MS-1 | Bloqueado |
| Messenger | `pages_messaging` | `POST /{PAGE_ID}/messages` | Sin aprobar ni enviar | Igual | MS-04, MS-05 | V-MS-2 | Bloqueado |
| Messenger | `pages_read_engagement` | Nombre y foto de la Página en la tarjeta | Sin aprobar. **No estaba en la configuración «Auphere Messenger»** el 2026-10-29 (T050 pendiente) | Según auditoría 2026-10-29 | MS-02 | V-MS-1 | Bloqueado por T050 |

## Reglas de grabación: oficiales y del equipo

Verificado hoy en la guía oficial de grabaciones ([screen recordings](https://developers.facebook.com/docs/app-review/submission-guide/screen-recordings)):

- **Oficial:** alta resolución, preferiblemente 1080p o más (es una recomendación).
- **Oficial:** interfaz en inglés si es posible. Si no, añadir explicaciones en pantalla.
- **Oficial:** el revisor no escucha el audio. Se recomiendan anotaciones.
- **Oficial:** mostrar el login completo desde la sesión cerrada.
- **Oficial:** mostrar cómo se concede el permiso, con el botón de login de negocio si existe.
- **Oficial:** mostrar después la función que usa ese permiso.
- **Oficial:** cubrir todos los permisos y funciones de la solicitud. Si falta alguno, la solicitud puede rechazarse.
- **Del equipo, no es requisito oficial:**
  - «Un vídeo por permiso». La guía no lo exige, pero sí que todos se vean.
  - 1 a 3 minutos por vídeo.
  - Subtítulos en lugar de audio.
- **Sin verificar hoy:** «al menos una llamada con éxito por permiso en 30 días». La página de grabaciones no lo menciona; según la auditoría, está en la guía de envío.

## Lo que Meta decide

Esta matriz mide la preparación técnica y las evidencias que tenemos. No predice la decisión de Meta. Los requisitos marcados como «según auditoría» deben contrastarse en la guía de envío vigente antes de enviar.
