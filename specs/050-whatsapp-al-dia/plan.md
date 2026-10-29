# Plan de implementación: 050 — WhatsApp al día (Meta 2026)

**Rama**: `develop` (decisión del owner) | **Fecha**: 2026-10-29 | **Spec**: [spec.md](spec.md)

**Entrada**: [spec.md](spec.md), [research.md](research.md) (contratos oficiales de Meta y lectura del código) y [whatsapp-antes-de-la-revision.md](../049-meta-instagram-messenger/whatsapp-antes-de-la-revision.md).

## Resumen

WhatsApp es el canal principal. El plan lo pone al día con Meta 2026 en cuatro iteraciones. Cada una se puede entregar y probar sola:

1. **Iteración 1 (P1, antes del 2026-11-16)**:
   - no perder nada: lotes completos e identidad por BSUID;
   - conexión vigente: registro integrado v4, una sola versión de Graph (v26.0), PIN guardado y reconexión que conserva la configuración;
   - salud de la cuenta y de las plantillas, con atribución por WABA;
   - bajas de marketing.
2. **Iteración 2 (P2)**: plantillas completas (cabecera multimedia, autenticación, carrusel); botones de plantilla, anuncio de origen, contactos, indicador de escritura y ubicación; precio por mensaje y límites en la consola.
3. **Iteración 3 (P2)**: catálogo de productos en la página del número de la consola nueva (crear, editar, borrar), herramientas de catálogo del agente por canal y material de revisión de `catalog_management` y `business_management`.
4. **Iteración 4 (P3)**: perfil del negocio.

## Contexto técnico

- **Lenguaje:** Python 3.12 (FastAPI, SQLAlchemy 2 async, Alembic, httpx) · TypeScript / Next.js 16 / React 19 (consola nueva de la spec 047 y panel).
- **Dependencias:** ninguna nueva.
- **Almacenamiento:** PostgreSQL. Una migración por iteración, encadenada sobre la cabeza de `develop` al empezar (hoy `0205_meta_social_channels`).
- **Pruebas:**
  - pytest: unidad del parser con cargas firmadas, integración de webhook, despachador y API, e isolation;
  - vitest de la consola y del panel;
  - staging con números reales.
- **Plataforma:** API y worker en AWS (ECS), consola en Vercel, Meta Graph `v26.0`.
- **Restricciones:**
  - ack del webhook en milisegundos (SLI `webhook_ack_ms` p95 < 50 ms) y nunca más de 20 s;
  - `only_waba_sharing` muere el 2026-11-16;
  - WhatsApp de hoy no puede cambiar para quien ya lo usa (CE-008).
- **Escala:** decenas de clientes y miles de mensajes al día; lotes de Meta de hasta 1000 elementos.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | **Garantía 1:** los eventos de WABA se aplican por `resolve_waba_tenants`, bajo la RLS de cada negocio. **Garantías 4 y 8:** `identifier` no se reescribe; el BSUID lo pone la plataforma; nunca se funden dos filas. Las herramientas de catálogo derivadas del canal se calculan por tenant y por turno. Pruebas: `tests/isolation/test_whatsapp_identity_bsuid.py`, `test_waba_event_attribution.py` y `test_catalog_tools_per_channel.py` |
| II | Superficie | ☑ | `0`, la misma de WhatsApp |
| III | Lo leído es dato | ☑ | El `referral` (titular, cuerpo), los nombres de perfil y los mensajes de sistema llegan como datos del turno, nunca como mensaje de sistema del operador |
| IV | Acción `mutates` | ☑ | Rotar el PIN, levantar una baja, crear y borrar productos y editar el perfil dejan auditoría con la persona. Borrar un producto pide confirmación con su nombre. Ninguna acción la hace el agente solo |
| V | Estados honestos | ☑ | Plantillas con estado, calidad y motivo. Canal con `problem_reason` y su origen. Catálogo en solo lectura con el porqué. Perfil en coexistencia: la sección no existe. Estados de vacío, carga, error y parcial en Catálogo |
| VI | Por API | ☑ | Todo por Graph y por la API de la consola |
| VII | Test primero | ☑ | Cada criterio EARS nace como test (ver `tasks.md`); el parser con cargas firmadas de cada campo; nada de `skip` |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | KB | ☑ | `ADR-027`, `02-embedded-signup`, `04-webhooks`, `13-meta-canales-investigacion-2026-10`. Al cerrar, nota de sesión y actualización de `04-webhooks` y `02-embedded-signup` |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Garantías 1, 4, 6 y 8 (ver arriba) | Una tarea por cada prueba en `tests/isolation/` |
| **Licencias** | Ninguna dependencia nueva | — |
| **Medidor** | Nada nuevo de modelo. Los mensajes de Meta se **muestran** (Consumo, «Mensajes de Meta») y no se cobran: Meta factura al negocio (Tech Provider) | Tarea de Consumo de la iteración 2 |

## Diseño

### Iteración 1

**Parser** (`apps/channels/src/nexus_channels/whatsapp_meta/webhook_adapter.py`)
- Iteradores por `change` para mensajes, estados, ecos, sincronización e historial.
- `_build_inbound` deja de exigir `from`.
- El evento normalizado lleva `sender_identifier` (teléfono o BSUID), `sender_bsuid`, `sender_phone` y `username`.
- Tipos `system`, `button`, `errors` y `referral` (los dos últimos se guardan en la iteración 2, pero se parsean ya).

**Router** (`apps/api/src/nexus_api/api/webhooks/meta.py`)
- Itera los elementos y aísla los fallos.
- Despacha los campos nuevos a `services/whatsapp_account_events.py` (cuenta, plantillas, límites, nombre, nombre de usuario) y a `services/whatsapp_opt_outs.py`.
- `account_update` con `waba_info` se atribuye por `resolve_waba_tenants`.

**Identidad**
- `apps/worker/src/nexus_worker/persistence/messages.py` pasa de `upsert_customer` a `upsert_customer_identity(bsuid, phone, username, name)`, con las reglas de [data-model.md](data-model.md). La usan el turno y los consumidores de coexistencia.
- El despachador (`streams/outbound.py`) elige `to` o `recipient`.

**Bajas**
- `whatsapp_opt_outs` con `scope`, `source` y `customer_id`.
- El despachador bloquea solo marketing con `scope=marketing`; las difusiones (`services/broadcasts.py`) también.

**Registro integrado**
- `signupExtras(mode, version)` en un módulo compartido. Consola, panel y enlace del dueño lo importan. Hay que comprobar el reparto de paquetes: si no hay un paquete compartido, se duplica la tabla con una prueba de paridad.
- `parseSignupMessage` acepta v4 y v5. Interruptor `meta_embedded_signup_version`, por defecto `v4`.

**Graph**
- `MetaClient(version=settings.meta_graph_api_version)` en todas sus construcciones.
- `meta_graph_api_version = "v26.0"`.
- Prueba que falla si aparece una versión escrita a mano en el código.

**Alta**
- `MetaCredentials.two_step_pin`.
- `_upsert_channel` fusiona `config` en vez de reemplazarlo.
- Rotación del PIN en el panel.

**Salud**
- `problem_reason` + `account_review` y `account_alert` (migración del CHECK).
- `config.problem_source`.
- `whatsapp_health_cron` solo limpia `quality`, lee `whatsapp_business_manager_messaging_limit` y `name_status`, y avisa de la caducidad de la versión.

**Consola**: la página del canal (spec 047) enseña nombre de usuario, nombre visible, límite, revisión y alertas. Las plantillas enseñan calidad y categoría pendiente. Notificaciones nuevas.

### Iteración 2

- **Plantillas:** `TemplateCreateIn` y el compositor (`template-composer.tsx`, `template-rules.ts`) ganan cabecera multimedia, autenticación y carrusel. `services/whatsapp_media_upload.py` (Resumable Upload) va **primero**: es el riesgo abierto D7.3. `_build_template_components` gana multimedia, copiar código y carrusel.
- **Entrantes:** `button`, `referral` (`conversations.ad_referral`) y `contacts` legibles.
- **Salientes:** el indicador de escritura junto al acuse (`runtime/read_receipts.py`); ramas `location` y `location_request` en el despachador; `notification.request_location` en el MCP; perfil de capacidades corregido.
- **Precio:** `messages.pricing_billable` y `pricing_type`. `GET /usage/meta-messages` y su bloque en Consumo, separado.

### Iteración 3 — Catálogo

- **`MetaClient`:** `create_catalog`, `create_product`, `update_product`, `delete_product`, `list_products(fields…)`, `product_feeds` y `commerce_settings`.
- **API:** `api/console/channel_catalog.py` (contrato en [console-api.md](contracts/console-api.md)), con `If-Match` en la edición.
- **Consola:** sección «Catálogo» en `components/builder/channel-page.tsx`.
  - Entra en `SECTIONS`, después del formulario y antes de las comprobaciones, con su propio guardado por producto.
  - Lista con buscador y filtro, y panel lateral de alta y edición con los componentes del sistema de diseño.
  - Al final de la iteración pasa la revisión de diseño (`impeccable` / `design:design-critique`) sobre la pantalla real.
- **Agente:** el conjunto de herramientas del turno es el de la versión del agente más las derivadas del canal (catálogo si el canal lo tiene), en el cargador del turno. Las herramientas filtran agotado, oculto y rechazado.
- **Revisión:** kit de `catalog_management` y `business_management` con número Cloud API; instrucciones del revisor unificadas con Instagram y Messenger.

### Iteración 4 — Perfil

`GET/PUT /channels/{id}/whatsapp-profile`, con la foto por Resumable Upload y una sección «Perfil» en la página del canal. En coexistencia la sección no existe (§V).

## Estructura

```text
specs/050-whatsapp-al-dia/{plan,research,data-model,quickstart}.md, contracts/{webhook-events,console-api}.md
apps/api/alembic/versions/0206_whatsapp_identity_and_health.py (it. 1), 0207_whatsapp_pricing_referral.py (it. 2)
apps/channels/src/nexus_channels/whatsapp_meta/{webhook_adapter,meta_client,adapter,signup,credentials}.py
apps/api/src/nexus_api/api/webhooks/meta.py
apps/api/src/nexus_api/services/{whatsapp_account_events,whatsapp_opt_outs,whatsapp_media_upload}.py
apps/api/src/nexus_api/api/console/{channel_catalog,whatsapp_profile,templates,usage}.py, admin/{whatsapp_pin,opt_outs}.py
apps/worker/src/nexus_worker/{persistence/messages.py, streams/outbound.py, runtime/read_receipts.py, streams/whatsapp_health_cron.py, streams/meta_*_consumer.py}
apps/mcp/src/nexus_mcp/servers/{notification,meta_catalog}/tools.py
apps/console/src/{lib/meta-fb-sdk.ts, components/builder/channel-page.tsx, components/channels/template-composer.tsx, app/(console)/usage/**}
apps/admin/src/{lib/meta-fb-sdk.ts, app/(dashboard)/tenants/[id]/**}
apps/api/tests/{unit,integration,isolation}/…, apps/channels/tests/fixtures/meta_webhooks/*.json
```

## Complexity Tracking

| Añadido | Por qué |
|---|---|
| `resolve_waba_tenants` (SECURITY DEFINER) | Los eventos de socio y de plantilla no traen número: sin atribución por WABA se pierden o, peor, se aplican mal. Solo devuelve ids, nunca filas |
| Herramientas de catálogo derivadas del canal | El owner pidió el catálogo para todos los números sin cambiar de plantilla. La lista blanca sigue siendo por tenant y por turno, calculada del estado del negocio; prueba de aislamiento propia |
| `customers.bsuid`/`phone` en vez de reescribir `identifier` | Reescribir rompería hilos y más de 15 sitios que esperan teléfono. Las columnas nuevas dan la identidad sin migrar datos de nadie |
| v5 del registro integrado detrás de un interruptor | Salió el 2026-10-20 y cambia `waba_id`. Se adopta cuando pasen las cinco vías en staging, no antes |
