# Investigación: Acceso a conectores por partner

Lo que había que decidir antes del diseño, con lo que dice el código de `develop` (`23e21fad`, 2026-11-13).

## D1 · El conector se identifica por su slug, no por una fila

**Decisión**: las dos tablas nuevas usan `connector_slug` (texto) y no una FK a `connectors.id`.

**Por qué**:
- Los conectores de Composio no tienen fila en `connectors` hasta el primer consentimiento. `list_catalog` los proyecta en vivo desde `composio.list_auth_configs()`, y `ensure_composio_connector_persisted` solo crea la fila al iniciar el consentimiento (`services/connectors/catalog.py:319-445`).
- Los dos caminos usan la misma clave, `ac.toolkit_slug.lower()` (`_project_dynamic`, `catalog.py:208`). Así que se puede restringir un conector que nadie ha conectado (requisito 1.5).

**Alternativa descartada**: crear la fila de `connectors` al restringir un conector de Composio. Obliga a llamar a Composio desde el panel para guardar una decisión, y deja filas sin conexión.

## D2 · Valor por defecto más decisión por partner, en dos tablas

**Decisión**:
- `connector_access_defaults (connector_slug PK, enabled, …)`: sin fila significa «habilitado».
- `connector_partner_access (connector_slug, partner_id, enabled, …)`, con PK compuesta.

La disponibilidad de un conector para un partner es `override.enabled` si hay fila y, si no, `default.enabled`. Si tampoco hay valor por defecto, está habilitado.

**Por qué**: una sola tabla con `partner_id NULL` para el valor por defecto no admite esa clave primaria y complica la unicidad. Con dos tablas, las dos vistas del panel (partner y conector) escriben las mismas filas de `connector_partner_access` (requisito 3.3).

## D3 · Sin RLS, como `connectors` y `platform_settings`

**Decisión**: las dos tablas son datos de plataforma, sin `tenant_id` y sin RLS, con `GRANT SELECT, INSERT, UPDATE, DELETE … TO nexus_app`, como `platform_settings` (`alembic/versions/0231_platform_settings.py:92`).

**Por qué**:
- El turno las lee dentro de `tenant_scoped_session`, que solo fija `app.tenant_id` (`core/tenant_context.py:115-128`) y no `app.partner_id`.
- Una RLS copiada de `partner_model_allowlist` (por `app.partner_id`) escondería todas las filas en el turno. Como sin fila significa «habilitado», eso **abriría** todo: un fallo abierto por invisibilidad.
- Ningún partner ni cliente las lee directamente. Solo las lee el servidor, que calcula el conjunto de slugs no disponibles para un cliente concreto.

**Test**: el de aislamiento pasa por el camino real del turno, con la sesión y el rol del worker, para cazar ese fallo. No llama a la regla directamente.

## D4 · «El partner de un cliente» es `tenants.partner_id`

**Decisión**: la regla usa `tenants.partner_id`, que es único por cliente. `NULL` significa sin partner, y entonces aplica el valor por defecto.

**Por qué**:
- `partner_tenants` admite, por su restricción, el mismo cliente bajo más de un partner (`UNIQUE (partner_id, tenant_id)`).
- `tenants.partner_id` es lo único que el turno, la consola y los procesos programados conocen igual.
- `tenants` no tiene RLS (`composio_proxy/proxy.py:209-212`), así que se lee dentro de la sesión del cliente.

## D5 · Dónde se aplica en el turno: `activations.tool_policy`, antes de todo `continue`

**Decisión**: `tool_policy` (`services/activations.py:134-211`) añade a `blocked` toda herramienta cuyo `Connector.slug` esté entre los no disponibles del cliente. La comprobación va **antes** de las ramas que hoy dejan pasar sin mirar: la de clientes que no son de la consola v2, y la de conexiones sin activaciones (`if not (strict or connection_id in managed): continue`).

**Por qué es suficiente para Composio**:
- Las herramientas de Composio entran al turno por `load_blueprints_for_tenant`, y salen de filas de `tool_catalog` con `connector_id` (`composio_proxy/proxy.py:258-277`).
- Esas filas son justo las que recorre `tool_policy` (join `ToolCatalog` → `Connector`).
- Una herramienta de Composio sin fila en el catálogo no llega al turno.

**Fallo**: `_load_tool_policy` ya falla cerrado (`pipeline.py:2521-2535`): si no puede leer, deja el turno sin herramientas de conectores. La nueva lectura va dentro de la misma función, así que hereda ese comportamiento (requisito 5.8). El alcance del fallo no crece, porque es una consulta más sobre la misma sesión.

## D6 · Los procesos programados se cortan en el cargador de la conexión

**Decisión**: los cargadores que resuelven la conexión de un cliente en `apps/mcp` comprueban la disponibilidad y fallan como «sin conexión» si el conector no está disponible:
- `_load_amigable_client` (`servers/amigable_cobro/tools.py:82`);
- `_load_woocommerce_client` (`servers/woocommerce/tools.py:~120`);
- el de `inventory` para Amigable Venta (`servers/inventory/tools.py:128`).

Esos cargadores los usan tanto las herramientas del turno como los procesos programados:
- `cobranza_reminder_cron` (`worker/streams/cobranza_reminder_cron.py:320`);
- `agent_sales_poll_cron` (`worker/streams/agent_sales_poll_cron.py:102`).

**Por qué en el cargador y no en cada proceso**: hay dos procesos hoy, y mañana habrá más. El cargador es el único punto por el que pasa cualquier uso de la credencial.

**El barrido**: un test unitario recorre con AST `apps/mcp/src` y `apps/worker/src`. Toda función que haga `select(TenantConnector` tiene que estar en una lista cerrada con su razón, o llamar a la comprobación (constitución §I: barrer, no enumerar).

**Fuera**: `connector_reconcile_cron` sigue reconciliando el estado con Composio. No usa la conexión para nada del negocio, y mantener el estado al día es lo que permite que todo vuelva intacto al rehabilitar (requisito 5.6).

## D7 · El alta se corta en el servicio, y un barrido lo vigila

**Decisión**: `ensure_connector_available(session, tenant, slug)` se llama en las funciones de `services/connectors/service.py` que crean o completan una conexión:
- `initiate_consent` (:347);
- `complete_consent_from_webhook` (:463), que deja la conexión `error` en vez de `connected` (el estado terminal de la máquina de estados) y no sincroniza herramientas;
- `bootstrap_browser_credentials` (:1089);
- `bootstrap_api_key` (:1147).

Por ellas pasan la consola (`/connectors/*/consent`, `/api-key`, `…/connections`), el panel (`initiate-consent`, `connect-api-key`, `reissue-consent`) y el alta por la API de partners (`partner_provisioning.py:101`).

`bootstrap_webhook_manual` es de canales y queda fuera.

**El barrido**: un test AST comprueba que toda construcción de `TenantConnector(` en `apps/api/src` está dentro de una función que llama a `ensure_connector_available` o que está en la lista cerrada de canales.

## D8 · El catálogo de la consola: `list_catalog` exige decir para quién

**Decisión**: `list_catalog` y `get_catalog_entry` reciben un argumento obligatorio, `audience: OPERATOR | ForTenant(tenant_id)`.
- Con `OPERATOR` devuelven todo (el panel).
- Con un cliente quitan los slugs no disponibles.

Así, `mypy --strict` obliga a decidir en cada llamada. Hoy hay tres: `admin/connectors.py:214`, `console/tools.py:297` y `console/agent_integrations.py:191`.

**Los dos listados que no pasan por `list_catalog`**:
- `capabilities_client._rows` (`console/capabilities_client.py:123`): consulta `ToolCatalog ⨝ Connector`. Quita las filas de slugs no disponibles.
- `agent_spec.validator.load_context` (`services/agent_spec/validator.py:405`). Marca `ToolInfo.withheld = True`, lo que la saca de `offered_connectors` (`validator.py:159`), y con ello el constructor y `missing.py` dejan de proponerla.

## D9 · Guardar un agente con herramientas retenidas no falla

**Decisión**: hoy `validate_spec` da `tool_not_allowed` si `not info.integration_offered` (`validator.py:295`).
- **Una herramienta retenida que ya estaba** en la versión guardada del agente (borrador o activa) no da problema: se conserva sin mostrarse (requisito 5.7).
- **Una retenida que se añade** da `tool_not_allowed`, igual que hoy una no ofrecida. Así una llamada directa a la API no la cuela (requisito 1.6).

`load_context` ya recibe `agent_id`, así que carga las herramientas de la versión guardada del agente en `Context.kept_withheld`. Hay que respetarlas en dos sitios:
- `validate_spec`;
- `missing.strip_doc` (`api/console/agent_draft_routes.py:405-414`). Hoy esa función quita sin rechazar «lo que no tenemos» (047, 65.3), y sin este cambio borraría las herramientas retenidas al guardar.

**La pantalla de capacidades**: no muestra esas herramientas (D8). Al guardar desde ella, `_set_spec_tools` conserva las que no se ven.

## D10 · Antes de quitar el acceso: 409 con la lista de afectados

**Decisión**: los `PUT` del panel que quitan acceso calculan los afectados en servidor:
- los clientes cuyo partner pierde el acceso y que tienen una conexión `connected`, `partial`, `needs_reauth` o `paused` de ese slug;
- los agentes con activación sobre esa conexión.

Si hay afectados y la petición no trae `confirm: true`, responden `409 confirm_required` con la lista y no guardan nada.

Si el slug es el `default_connector_slug` de un partner que pierde el acceso, responden `409 partner_default_connector`, aunque venga `confirm`, nombrando el partner (requisitos 4.3 y 4.4).

**Por qué no un endpoint de vista previa aparte**: con un solo endpoint, la comprobación se repite en cada guardado. Las conexiones se leen cliente a cliente, cada uno con su propia sesión y su RLS, como `/admin/connectors-installs`, así que no pueden ir en la misma transacción que la escritura. Si entre la lectura y la escritura se conecta un cliente nuevo, el cambio se guarda igual: la regla se aplica en el turno de todos modos.

## D11 · La auditoría sigue el patrón de `partner_access`

**Decisión**: `AuditLog(tenant_id=None, actor=operator_actor(op), action=…, target=…, before_json, after_json)`, con el motivo dentro de `after_json.reason`. Es el mismo patrón que `admin/partner_access.py:160-181`.

Dos acciones nuevas en `console_audit_vocabulary`, sembradas en la migración como en la 0231:
- `connector_access.default_changed`;
- `connector_access.partner_changed`.

## D12 · Quedan fuera los canales y los conectores de sistema

- **Canales**: `provider_meta.channel_only` (`console/tools.py:87`).
- **Sistema**: `SYSTEM_ONLY_CONNECTORS = {"googlecalendar"}` (`services/connectors/service.py:83`).

El panel no ofrece cambiarlos, y la API rechaza con `422 connector_not_managed`. La regla los ignora aunque hubiera una fila antigua.

## Licencias

Sin dependencias nuevas.

## D13 · «No disponible» y «no existe» responden igual

`ConnectorUnavailable` es un `ConnectorNotFound` (`services/connectors/errors.py`) con el mismo texto. Todos los manejadores que ya respondían 404 a un slug desconocido responden igual a uno no disponible, sin tocarlos uno a uno. En `connection_of` (activar, desactivar y `/connections`) es el mismo `unknown_integration`. En `start_consent`, el mismo texto que da Composio para un slug que no conoce (`catalog.unknown_connector_message`).
