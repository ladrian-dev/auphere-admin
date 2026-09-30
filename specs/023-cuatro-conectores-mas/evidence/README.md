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
