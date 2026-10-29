# WhatsApp antes del envío a revisión de Meta (2026-10-29)

Cruce de la documentación oficial de Meta (WhatsApp Cloud API, Embedded Signup, permisos, App Review) con lo que hace hoy el código de `develop`. Meta revisa **la app entera** en cada envío y una solicitud enviada no se puede editar: lo que se quiera pedir entra en el mismo envío que Instagram y Messenger, y lo que no se use no se pide.

## 1. Qué pedir en el envío

| Permiso | ¿Pedirlo? | Por qué |
|---|---|---|
| Instagram y Messenger (spec 049) | **Sí** | Construido; falta grabar los vídeos |
| `catalog_management` | **Sí, con condición** | El código lo usa (catálogo en el número, spec 022). La guía oficial pide grabar **crear, editar y borrar** un catálogo o sus productos desde Auphere; hoy solo listamos, enlazamos y leemos. Hace falta un número **Cloud API** en la demo del revisor: en coexistencia Meta no deja listar catálogos |
| `business_management` | **Solo como dependencia** | Solo lo usa `GET /{business}/owned_product_catalogs`. La guía oficial de su vídeo pide mostrar **datos de anuncios** (impresiones, gasto…), que Auphere no tiene: es el rechazo más probable. Describirlo nombrando el permiso del que depende (`catalog_management`, Messenger) y su uso real |
| `whatsapp_business_manage_events` | **No** | Conversions API para medir anuncios; no hay ningún uso en el código. Pedirlo sin uso es causa de rechazo. Si un día se integra, se aprueba solo porque ya tenemos `whatsapp_business_messaging` |
| `ads_read` | **No** | Sin métricas de anuncios |
| Calling, Groups, BSUID y nombres de usuario, indicador de escritura, Marketing Messages API (envío) | **No hace falta pedir nada** | Van con `whatsapp_business_messaging` / `whatsapp_business_management`, ya aprobados |

## 2. Fallos encontrados en el código

| # | Fallo | Estado |
|---|---|---|
| F1 | `notification.send_template` rechazaba **toda plantilla aprobada** que hubiera recibido el webhook de estado: el webhook guarda `"APPROVED"` y la herramienta comparaba con `"approved"` | **Corregido** (`c3bffbee`), con prueba |
| F2 | Si un mensaje llega **sin `from`** (persona con nombre de usuario de WhatsApp, BSUID), el parser lo descarta en silencio (`webhook_adapter.py:491-494`). Meta exige a todos los partners soportar BSUID | Pendiente. **El más urgente** |
| F3 | De cada lote del webhook solo se procesa el primer mensaje, el primer estado y el primer eco (`parse_inbound`, `parse_status_callback`) | Pendiente; verificar con tráfico real si Meta agrupa estados |
| F4 | Pulsar un botón de respuesta rápida de **plantilla** (`type=button`) llega como `[unsupported:button]` | Pendiente |
| F5 | El PIN de dos pasos que se genera al registrar el número no se guarda en ningún sitio | Pendiente |
| F6 | `account_update` exige `value.phone_number`; los eventos de socio (app retirada, WABA dada de baja) pueden traer solo `waba_info` y se ignorarían | Pendiente; verificar con un payload real |

## 3. Cambios de Meta que nos afectan

| Cambio | Desde | Qué hacer |
|---|---|---|
| Embedded Signup v2/v3 deprecados: se sirven como v4; `only_waba_sharing` deja de funcionar | 2026-10-15 · 2026-11-16 | Pasar las configuraciones a v4 (o v5: `extras.version:"v5"`, sin `sessionInfoVersion`). Hoy enviamos `sessionInfoVersion: "3"` |
| Graph API: WhatsApp usa **v22.0 fijo** en `meta_client.py`; v21 caduca el 2027-01-21 y v22 después | — | Subir a v25/v26 y hacer que `meta_graph_api_version` mande de verdad en el servidor |
| Precio: servicio gratis solo hasta 1000 mensajes por número al mes; utilidad dentro de la ventana se cobra | 2026-10-01 | Guardar `pricing.billable` / `type` del webhook de estado (hoy solo la categoría) y revisar el coste del agente |
| Límites de mensajería por portafolio; `messaging_limit_tier` deprecado | 2025-10-08 | Leer `whatsapp_business_manager_messaging_limit` |
| BSUID en webhooks, envío por BSUID, nombres de usuario | abril–julio 2026 | Ver F2: clave por `user_id`, `from`/`wa_id` opcionales, campo `recipient`, webhook `business_username_updates` |

## 4. Funciones que faltan y valen la pena (sin permiso nuevo)

Por orden de valor para los clientes de Auphere:

1. **Webhooks suscritos pero descartados**: `user_preferences` (baja de marketing, `stop`/`resume`), `message_template_quality_update`, `template_category_update`, `account_alerts`, `account_review_update`, `business_capability_update`, `phone_number_name_update`. Hoy acaban en `webhook.meta.unhandled_field`.
2. **Indicador de escritura** mientras el agente piensa.
3. **Respuesta a botones de plantilla** (F4) y **`referral`** de anuncios click-to-WhatsApp (de qué anuncio viene el cliente).
4. **Plantillas**: cabecera con imagen, botón de copiar código (sin él, las de autenticación las rechaza Meta), carrusel.
5. **Ubicación nativa** (hoy sale como texto) y **petición de ubicación**.
6. **Perfil del negocio** (`whatsapp_business_profile`): foto, descripción, horario desde la consola.

Fuera de alcance por ahora: Flows, Calling, Groups (exige cuenta oficial), Payments (solo India y Brasil), Marketing Messages API.

## 5. Orden propuesto

1. F2 (BSUID) y F3, antes que nada: pueden estar perdiendo mensajes hoy.
2. Embedded Signup v4/v5 y Graph v25+ antes del 2026-11-16.
3. Webhooks de §4.1 y el precio por mensaje.
4. Demo del revisor con número Cloud API y la pantalla de catálogo que crea, edita y borra productos; después, el envío único con Instagram, Messenger, `catalog_management` y `business_management`.

Fuentes: los informes de esta sesión. Docs oficiales: `developers.facebook.com/documentation/business-messaging/whatsapp/*` (permissions, solution-providers/app-review, embedded-signup/versions, business-scoped-user-ids, pricing, messaging-limits, webhooks/overview, changelog) y `developers.facebook.com/docs/permissions`.
