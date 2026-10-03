# Fase 0 — investigación

Seis decisiones, medidas contra el código y contra el catálogo público de
herramientas del proveedor de consentimientos el 2026-09-30. Una de ellas
(D1) lleva una comprobación fuera del repositorio antes de cerrar la
iteración 1: confirmar en el panel que cada slug de la lista cerrada existe.

---

## D0 · Lo que ya existe y no hay que rehacer

| Pieza | Dónde | Estado |
|---|---|---|
| El catálogo de conectores lee las *auth configs* del panel y las proyecta como `oauth_composio` | `services/connectors/catalog.py::list_catalog` → `_project_dynamic` | existe; los tres nuevos ya aparecen (en «otros») |
| Conectar por consentimiento y sincronizar al volver | `service.py::initiate_consent`, `complete_consent`, `sync_tools_for` | existe; no cambia |
| Sincronizar herramientas: **todas** las del toolkit, gateadas por `_derive_annotations` | `service.py::sync_tools_for` (líneas 545–650) | existe; **aquí entra la lista cerrada** |
| Pistas de lectura / escritura por slug | `service.py::_TOOL_SLUG_ANNOTATIONS` (24 entradas; 4 de Calendly, una de ellas con un slug que no existe) | existe; se sustituye para los tres por la lista cerrada |
| Lo desconocido nace bloqueado | `_default_mode_for` + `auto_enable_destructive=False` para los dinámicos | existe; no cambia |
| Encender al conectar lo que nace `always` | `service.py::auto_enable_connector_tools` (versión STAGED del agente) | existe; no cambia |
| Categoría del conector | `catalog.py::_resolve_category` (`_CATEGORY_MAP` + `_CATEGORY_KEYWORDS`); «payment», «commerce» caen en «otros» | existe; se amplía |
| Nombres de negocio de las capacidades | `api/console/capability_names.py::CAPABILITY_NAMES` (60 entradas, ninguna de un toolkit de Composio) | existe; se amplía |
| Frase de cada conector en la tarjeta | `apps/console/src/i18n/lanes/capabilities.ts` (`connectors.desc.<slug>`, reserva `connectors.desc.fallback`), resuelta en `components/integrations/connector-card.tsx:351` | existe; se amplía |
| «Recomendada» en Capacidades | `capabilities_client.py::_recommended(sector)` = `tools_required` de la plantilla del sector | existe **solo para capacidades**; la tarjeta de conector no tiene el concepto (la spec lo daba por hecho: corrección en D4) |
| Plantillas de sector | `services/templating/seeds/*_v1.yaml` (`tools.required`); `SeedTemplate` en `seed_templates.py` | existe; gana un campo |
| Fake del proveedor para tests | `composio_client.py::FakeComposioClient` (`register_tools`), fixture `fake_composio` en `tests/integration/connectors/conftest.py` | existe |

---

## D1 · La lista cerrada vive en código, por toolkit, y filtra la sincronización

**Alternativas**: (a) seguir sincronizando todo y esconder en la consola;
(b) una tabla en base de datos editable desde Admin; (c) una lista en código
por toolkit. El owner eligió una lista cerrada escrita por Auphere
(Clarifications). Se descarta (a) porque las 426 filas de Stripe seguirían
entrando en `tool_catalog` y en la lista blanca del agente. Se descarta (b)
porque «cambiar la lista es un cambio de Auphere» (Requisito 2.4) y una
tabla editable lo convertiría en un cambio de operador sin revisión.

**Decisión**: módulo nuevo `services/connectors/toolkits.py` con

```python
TOOLKIT_ALLOWLISTS: dict[str, dict[str, ToolHint]]   # toolkit → slug → {"read_only", "destructive"}
```

para `stripe`, `calendly` y `hubspot`. En `sync_tools_for`, **si el toolkit
tiene lista**, las herramientas que devuelve el proveedor se filtran a la
lista antes de tocar `tool_catalog`; las anotaciones de esas filas salen de
la lista (es la palabra de Auphere, Requisito 2.5), no de la heurística ni de
las etiquetas del proveedor. Los toolkits **sin** lista (Google Calendar,
Notion, Gmail…) siguen exactamente como hoy.

Dos registros nuevos, por el Requisito 2.4:

- `connector.sync.allowlist_missing` con los slugs de la lista que el
  proveedor **no** devolvió (una herramienta retirada, o un slug mal escrito
  aquí). Esa fila no se inventa; si existía, el bucle de hoy la marca
  `deprecated` y deja de verse.
- `connector.sync.allowlist_dropped` con cuántas devolvió el proveedor fuera
  de la lista (una nueva no entra sola).

La auditoría `connector.tools.synced` lleva `missing` y `dropped_count` en
`after`, para que se vea sin abrir logs.

La entrada `CALENDLY_CANCEL_EVENT` de `_TOOL_SLUG_ANNOTATIONS` (slug que no
existe) se retira junto con las otras tres de Calendly: la lista las
sustituye.

### Las listas, escritas contra el catálogo real

Leídas el 2026-09-30 del panel (Calendly, 53 herramientas, completo) y del
catálogo público del proveedor (`docs.composio.dev/toolkits/{stripe,hubspot}`,
que lista tools y triggers; los triggers se descartan). Los slugs de Stripe y
HubSpot se **confirman uno a uno en el panel** en la iteración 1 (tarea
propia); si alguno no existe, el registro `allowlist_missing` lo dirá el
primer día y la lista se corrige.

**Stripe — 12** (8 leen, 4 escriben)

| Slug | Lee / escribe | Nombre de negocio |
|---|---|---|
| `STRIPE_SEARCH_CUSTOMERS` | lee | Buscar un cliente |
| `STRIPE_SEARCH_PAYMENT_INTENTS` | lee | Ver el estado de un cobro |
| `STRIPE_RETRIEVE_PAYMENT_INTENT` | lee | Ver el detalle de un cobro |
| `STRIPE_LIST_INVOICES` | lee | Ver las facturas de un cliente |
| `STRIPE_LIST_PAYMENT_LINKS` | lee | Ver los enlaces de pago |
| `STRIPE_LIST_PRODUCTS` | lee | Consultar productos |
| `STRIPE_LIST_PRICES` | lee | Consultar precios |
| `STRIPE_LIST_REFUNDS` | lee | Ver reembolsos |
| `STRIPE_CREATE_CUSTOMER` | escribe | Dar de alta un cliente |
| `STRIPE_CREATE_PAYMENT_LINK` | escribe | Crear un enlace de pago |
| `STRIPE_CREATE_REFUND` | escribe | Reembolsar un cobro |
| `STRIPE_SEND_INVOICE` | escribe | Enviar una factura |

CE-001 («responde si un cobro está pagado y manda un enlace de pago» sin
que Auphere intervenga) se cumple con lecturas: el estado sale de
`SEARCH_PAYMENT_INTENTS` y el enlace de `LIST_PAYMENT_LINKS` (los enlaces
que el negocio ya tiene creados). Crear un enlace nuevo escribe y nace
bloqueado.

**Calendly — 10** (7 leen, 3 escriben)

| Slug | Lee / escribe | Nombre de negocio |
|---|---|---|
| `CALENDLY_WHO_AM_I` | lee | Identificar la agenda conectada |
| `CALENDLY_LIST_EVENT_TYPES` | lee | Ver los tipos de cita |
| `CALENDLY_LIST_EVENT_TYPE_AVAILABLE_TIMES` | lee | Consultar huecos |
| `CALENDLY_LIST_SCHEDULED_EVENTS` | lee | Ver las citas reservadas |
| `CALENDLY_GET_EVENT` | lee | Ver una cita |
| `CALENDLY_LIST_EVENT_INVITEES` | lee | Ver quién tiene la cita |
| `CALENDLY_LIST_USER_BUSY_TIMES` | lee | Ver cuándo está ocupado |
| `CALENDLY_POST_INVITEE` | escribe | Reservar una cita |
| `CALENDLY_CREATE_SINGLE_USE_SCHEDULING_LINK` | escribe | Crear un enlace de reserva |
| `CALENDLY_CANCEL_SCHEDULED_EVENT` | escribe | Cancelar una cita |

`WHO_AM_I` entra porque la API de Calendly exige la URI del usuario para
listar tipos de cita y citas; sin ella el agente no puede empezar.

**HubSpot — 11** (6 leen, 5 escriben)

| Slug | Lee / escribe | Nombre de negocio |
|---|---|---|
| `HUBSPOT_SEARCH_CONTACTS` | lee | Buscar un contacto |
| `HUBSPOT_LIST_CONTACT_NOTES` | lee | Ver las notas de un contacto |
| `HUBSPOT_SEARCH_DEALS` | lee | Buscar una oportunidad |
| `HUBSPOT_GET_DEAL` | lee | Ver una oportunidad |
| `HUBSPOT_SEARCH_TICKETS` | lee | Buscar una incidencia |
| `HUBSPOT_GET_TICKET` | lee | Ver una incidencia |
| `HUBSPOT_CREATE_CONTACT` | escribe | Dar de alta un contacto |
| `HUBSPOT_UPDATE_CONTACT` | escribe | Cambiar los datos de un contacto |
| `HUBSPOT_CREATE_NOTE` | escribe | Anotar en la ficha |
| `HUBSPOT_CREATE_DEAL` | escribe | Abrir una oportunidad |
| `HUBSPOT_CREATE_TICKET` | escribe | Abrir una incidencia |

Borrar o archivar (`HUBSPOT_ARCHIVE_*`, `STRIPE_DELETE_*`,
`CALENDLY_DELETE_*`) queda fuera de las listas: no hace falta en una
conversación y la constitución dice que borrar no existe.

---

## D2 · La categoría se decide por toolkit, no por lo que publique el proveedor

Hoy `_resolve_category` depende de la categoría que publica el proveedor
para el toolkit; «payments» y «commerce» no casan con ninguna palabra clave y
caen en «otros». Ampliar solo las palabras clave dejaría el Requisito 1.1 a
merced de un cambio de etiqueta ajeno.

**Decisión**: `catalog.py` gana `_CATEGORY_BY_TOOLKIT = {"stripe": "billing",
"calendly": "booking", "hubspot": "crm"}`, consultado **antes** que la
metadata. Además `_CATEGORY_MAP` y `_CATEGORY_KEYWORDS` aprenden
`payment`/`billing`/`financ`/`invoic` → `billing` y
`commerce`/`shop`/`store` → `ecommerce`, para que el siguiente conector de
cobros o de tienda no caiga en «otros» aunque no tenga entrada fija. Las
claves `int.cat.billing` («Cobros»), `int.cat.booking` («Citas») e
`int.cat.crm` («Clientes») ya existen en la consola.

---

## D3 · Nombres de negocio: una entrada por slug, y un test que no deja hueco

**Decisión**: `CAPABILITY_NAMES` gana las 33 entradas de arriba con clave
`("tool", "<SLUG>")` — la clave es el `tool_catalog.name`, que para los
dinámicos es el slug — y función `orders` para Stripe (la misma que las de
Amigable Cobro), `appointments` para Calendly y `other` para HubSpot (no hay
función «clientes» y no se inventa una para tres conectores; si llega un
cuarto de CRM, se abre). Sin `sectors`: son comunes a todos.

El Requisito 3.2 nace como test: `test_every_allowlisted_slug_has_a_business_name`
recorre `TOOLKIT_ALLOWLISTS` y falla si a un slug le falta nombre o
descripción en cualquiera de los dos idiomas. Añadir un slug sin nombre no
compila la suite.

Las descripciones dicen qué hace la capacidad en la conversación, no qué
endpoint llama; nada de «PaymentIntent», «invitee» ni «deal».

---

## D4 · «Recomendado» en la tarjeta de conector: campo nuevo, decidido por la plantilla

La spec suponía que «recomendado» ya existía en Conectores; medido, existe
solo en Capacidades (`CapabilityOut.recommended`), y sale de
`tools_required` de la plantilla, que nombra herramientas nativas
(`booking.*`, `billing.*`), no conectores. Recomendar un **conector** no se
puede deducir de ahí sin acoplar slugs de Composio a las plantillas, y
meterlos en `tools_required` intentaría encender herramientas que no existen
hasta que el partner conecte.

**Decisión**: las plantillas ganan un bloque opcional

```yaml
connectors:
  recommended: [agendapro, calendly]
```

leído por `load_seed_template` en `SeedTemplate.connectors_recommended`
(vacío si falta). `ConnectorOut` gana `recommended: bool`, que
`_connectors` rellena con `slug in template.connectors_recommended` para el
sector del cliente (reutiliza `client_sector` y la misma tolerancia que
`_recommended`: sin plantilla, nadie es recomendado). La tarjeta enseña la
insignia con el copy que ya existe (`cap.badge.recommended`, «Recomendada
para tu sector» → en la tarjeta «Recomendado para tu sector», clave nueva
`connectors.badge.recommended` porque el género cambia).

| Plantilla | `connectors.recommended` |
|---|---|
| barbershop, beauty_salon, clinica, dental, medspa, nail_studio, spa, aesthetic_clinic | `[agendapro, calendly]` |
| cobranza | `[amigable_cobro, stripe]` |
| woocommerce_sales, inventario | `[woocommerce]` (Shopify cuando exista) |
| restaurante, generic | ninguno |

Recomendar no filtra ni ordena: la tarjeta sigue en su categoría; solo lleva
la insignia (Requisito 4.2).

---

## D5 · La frase de cada conector

Tres claves en `capabilities.ts`, mismo registro que las cinco que hay:

| Clave | es | en |
|---|---|---|
| `connectors.desc.stripe` | Los cobros del negocio: si un pago está hecho, sus facturas y los enlaces de pago. | The business's payments: whether a charge is paid, its invoices and payment links. |
| `connectors.desc.calendly` | La agenda del negocio en Calendly: huecos libres, citas reservadas y quién viene. | The business's Calendly calendar: free slots, booked appointments and who is coming. |
| `connectors.desc.hubspot` | Los contactos del negocio en HubSpot: buscar a quien escribe, sus notas y sus oportunidades. | The business's HubSpot contacts: find whoever is writing, their notes and their deals. |

Sin nombres técnicos ni siglas; «CRM» no aparece.

---

## D6 · Aislamiento, licencias, medidor

- **Aislamiento**: ninguna garantía cambia. Las filas de `tool_catalog` de un
  conector dinámico son globales por diseño (el catálogo es de plataforma);
  la cuenta conectada (`tenant_connectors`) y la lista blanca del agente son
  por tenant y las decide la RLS, como hoy. No entra ninguna lectura nueva.
  Se añade un test de integración, no de aislamiento: sincronizar con la
  lista cerrada no toca filas de otro conector.
- **Licencias**: ninguna dependencia nueva.
- **Medidor**: nada nuevo. Las herramientas de Composio ya se ejecutan por
  `execute_tool` y se miden como herramienta de pago cuando lo son.
