# Evidencia — spec 023

## Panel de Composio (proyecto `auphere`, workspace `contacto_workspace`) — 2026-09-30

Hecho con la sesión del owner desde su navegador:

| Toolkit | Auth config | Esquema | Credenciales |
|---|---|---|---|
| Stripe | `ac_iZ3ED0FUpQ9k` (`stripe`) | OAuth 2.0 | Composio Managed · scope `read_write` |
| Calendly | `ac_SdfXGruGLskY` (`calendly`) | OAuth 2.0 | Composio Managed |
| HubSpot | `ac_21rDpFfZSjT3` (`hubspot`) | OAuth 2.0 | Composio Managed · 33 scopes por defecto |
| **Shopify** | **no creada** | OAuth 2.0 / Server-to-Server | **Composio no ofrece «managed» para Shopify**: pide Client ID y Client Secret de una app propia de Shopify Partners. Hasta que exista esa app, Shopify no entra |

Las cinco anteriores (gmail, googlecalendar, notion, googlesheets, outlook)
siguen igual. En cuanto la consola lea el catálogo, los tres nuevos aparecen
en «otros» con nombres técnicos: es lo que esta spec arregla.

## Lo que miden los toolkits (dashboard de Composio, 2026-09-30)

| Toolkit | Herramientas | Triggers |
|---|---|---|
| Stripe | **426** | 40 |
| HubSpot | **262** | 2 |
| Calendly | 53 | 10 |

**Hallazgo para el plan**: la consola hoy sincroniza *todas* las herramientas
de un conector (`composio.list_tools`) y gatea cada una por la tabla de pistas.
Con Stripe eso serían 426 capacidades en la pantalla, casi todas bloqueadas y
con nombre técnico (terminales de pago, disputas, relojes de prueba…). La
tabla de pistas no basta: hace falta una **lista cerrada por toolkit** (las
8–12 que el agente de un negocio usa: consultar productos y precios, estado
de un cobro, enlace de pago; huecos, citas, cancelar; buscar y crear
contacto, anotar), y que lo que no esté en ella **no llegue** a Capacidades.
Es una decisión de `/speckit-clarify`, no de implementación.

## Slugs reales de Calendly (panel de Composio, v20260929_00, 53 herramientas) — leídos el 2026-09-30

Lectura (candidatas a nacer encendidas): `CALENDLY_WHO_AM_I`, `CALENDLY_LIST_EVENT_TYPES`, `CALENDLY_LIST_EVENT_TYPE_AVAILABLE_TIMES`, `CALENDLY_LIST_SCHEDULED_EVENTS`, `CALENDLY_GET_EVENT`, `CALENDLY_GET_EVENT_TYPE`, `CALENDLY_LIST_EVENT_INVITEES`, `CALENDLY_GET_EVENT_INVITEE`, `CALENDLY_LIST_USER_BUSY_TIMES`, `CALENDLY_LIST_USER_AVAILABILITY_SCHEDULES`, `CALENDLY_GET_EVENT_TYPE_AVAILABILITY`, `CALENDLY_LIST_USER_LOCATIONS`.

Escritura (nacen bloqueadas): `CALENDLY_POST_INVITEE` (crear cita, plan de pago), `CALENDLY_CREATE_SCHEDULING_LINK`, `CALENDLY_CREATE_SINGLE_USE_SCHEDULING_LINK`, `CALENDLY_CANCEL_SCHEDULED_EVENT`, `CALENDLY_CREATE_EVENT_TYPE`, `CALENDLY_UPDATE_EVENT_TYPE`, `CALENDLY_UPDATE_EVENT_TYPE_AVAILABILITY`.

Fuera de la lista cerrada (organización, grupos, webhooks, formularios de enrutado, invitaciones, Enterprise): `CALENDLY_LIST_ACTIVITY_LOG_ENTRIES`, `CALENDLY_LIST_OUTGOING_COMMUNICATIONS`, `CALENDLY_*_ORGANIZATION*`, `CALENDLY_*_GROUP*`, `CALENDLY_*_WEBHOOK*`, `CALENDLY_*_ROUTING_FORM*`, `CALENDLY_CREATE_SHARE`, `CALENDLY_DELETE_*`, `CALENDLY_REMOVE_USER_FROM_ORGANIZATION`, `CALENDLY_REVOKE_USER_S_ORGANIZATION_INVITATION`, `CALENDLY_GET_INVITEE_NO_SHOW`.

Hallazgo: la tabla de pistas actual cita `CALENDLY_CANCEL_EVENT`, que no existe; el slug real es `CALENDLY_CANCEL_SCHEDULED_EVENT`.

Pendiente: leer del panel los slugs de Stripe (426) y HubSpot (262) con búsquedas dirigidas (customers, payment_links, checkout, invoices, refunds; contacts, deals, tickets). El panel devolvió 429 (límite de cinco horas, se reinicia 2026-09-30 17:10 UTC).
