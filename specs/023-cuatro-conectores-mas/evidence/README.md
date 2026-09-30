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

## Slugs de Stripe y HubSpot (catálogo público del proveedor, `docs.composio.dev/toolkits/{stripe,hubspot}`) — leídos el 2026-09-30

El panel devolvió 429 al leer Calendly (límite de cinco horas); Stripe y
HubSpot se leyeron del catálogo público, que lista **tools y triggers**
(`STRIPE_CHARGE_SUCCEEDED`, `HUBSPOT_CONTACT_CREATED_TRIGGER`… son triggers
y se descartan) y puede incluir herramientas ya retiradas del panel. Por eso
la lista cerrada del plan (`research.md`, D1) se **confirma slug a slug en el
panel** en la iteración 1 y, además, la sincronización registra
`allowlist_missing` si alguno no existe.

Extraídos: 473 identificadores `STRIPE_*` y 269 `HUBSPOT_*` (con triggers y
ruido). Familias relevantes para una conversación, tal cual aparecen:

- **Stripe, lectura**: `STRIPE_LIST_CUSTOMERS`, `STRIPE_SEARCH_CUSTOMERS`, `STRIPE_RETRIEVE_CUSTOMER`, `STRIPE_LIST_PAYMENT_INTENTS`, `STRIPE_SEARCH_PAYMENT_INTENTS`, `STRIPE_RETRIEVE_PAYMENT_INTENT`, `STRIPE_LIST_INVOICES`, `STRIPE_SEARCH_INVOICES`, `STRIPE_LIST_PAYMENT_LINKS`, `STRIPE_GET_PAYMENT_LINK`, `STRIPE_LIST_PRODUCTS`, `STRIPE_SEARCH_PRODUCTS`, `STRIPE_LIST_PRICES`, `STRIPE_SEARCH_PRICES`, `STRIPE_LIST_REFUNDS`, `STRIPE_LIST_CHARGES`, `STRIPE_SEARCH_CHARGES`, `STRIPE_LIST_CHECKOUT_SESSIONS`, `STRIPE_RETRIEVE_BALANCE`.
- **Stripe, escritura**: `STRIPE_CREATE_CUSTOMER`, `STRIPE_UPDATE_CUSTOMER`, `STRIPE_CREATE_PAYMENT_LINK`, `STRIPE_CREATE_CHECKOUT_SESSION`, `STRIPE_CREATE_PAYMENT_INTENT`, `STRIPE_CREATE_REFUND`, `STRIPE_CREATE_CHARGE_REFUND`, `STRIPE_CREATE_INVOICE`, `STRIPE_SEND_INVOICE`, `STRIPE_FINALIZE_INVOICE`, `STRIPE_VOID_INVOICE`, `STRIPE_CREATE_PRODUCT`, `STRIPE_CREATE_PRICE`, `STRIPE_CREATE_COUPON`, `STRIPE_CREATE_PROMOTION_CODE`, `STRIPE_DELETE_CUSTOMER`, `STRIPE_DELETE_PRODUCT`, `STRIPE_CANCEL_SUBSCRIPTION`.
- **Stripe, fuera**: terminales, disputas, relojes de prueba, Connect, medidores de facturación, Financial Connections, Climate, suscripciones (no las vende ningún partner hoy).
- **HubSpot, lectura**: `HUBSPOT_SEARCH_CONTACTS`, `HUBSPOT_SEARCH_CONTACTS_BY_CRITERIA`, `HUBSPOT_LIST_CONTACTS`, `HUBSPOT_GET_CONTACTS`, `HUBSPOT_READ_CONTACT`, `HUBSPOT_LIST_CONTACT_NOTES`, `HUBSPOT_LIST_CONTACT_TASKS`, `HUBSPOT_SEARCH_DEALS`, `HUBSPOT_GET_DEAL`, `HUBSPOT_LIST_DEALS`, `HUBSPOT_SEARCH_TICKETS`, `HUBSPOT_GET_TICKET`, `HUBSPOT_LIST_TICKETS`, `HUBSPOT_SEARCH_COMPANIES`, `HUBSPOT_GET_COMPANY`, `HUBSPOT_RETRIEVE_OWNERS`, `HUBSPOT_RETRIEVE_PIPELINE_STAGES`, `HUBSPOT_SEARCH_PRODUCTS`.
- **HubSpot, escritura**: `HUBSPOT_CREATE_CONTACT`, `HUBSPOT_UPDATE_CONTACT`, `HUBSPOT_UPSERT_CONTACTS`, `HUBSPOT_CREATE_NOTE`, `HUBSPOT_CREATE_TASK`, `HUBSPOT_CREATE_MEETING`, `HUBSPOT_CREATE_DEAL`, `HUBSPOT_UPDATE_DEAL`, `HUBSPOT_CREATE_TICKET`, `HUBSPOT_UPDATE_TICKET`, `HUBSPOT_CREATE_COMPANY`, `HUBSPOT_ARCHIVE_CONTACT`, `HUBSPOT_ARCHIVE_DEALS`, `HUBSPOT_REMOVE_DEAL`, `HUBSPOT_DELETE_NOTE`.
- **HubSpot, fuera**: campañas y correos de marketing, propiedades y esquemas, importaciones, plantillas de línea de tiempo, extensiones de llamadas, envíos de feedback, lotes (`*_BATCH_*`), «desde lenguaje natural» (`*_FROM_NL`: el agente ya entiende lenguaje natural; no hace falta que lo haga el proveedor).

La lista cerrada elegida (12 · 10 · 11) y los nombres de negocio están en
`research.md` (D1).
