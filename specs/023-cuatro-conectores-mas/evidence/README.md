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
