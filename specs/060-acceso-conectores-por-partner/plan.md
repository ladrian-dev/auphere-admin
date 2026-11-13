# Implementation Plan: Acceso a conectores por partner

**Branch**: `060-acceso-conectores-por-partner` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/060-acceso-conectores-por-partner/spec.md`

## Summary

**Datos.** Cada conector gana un valor por defecto para los partners, y cada par conector y partner puede tener una decisión propia. La regla vive en un módulo, `services/connectors/availability.py`, y responde una pregunta: qué slugs no están disponibles para este cliente.

**Dónde se aplica:**
1. el catálogo que ve la consola;
2. el alta de una conexión;
3. la política de herramientas del turno;
4. los cargadores de credenciales que usan los procesos programados.

Dos barridos AST vigilan que ningún camino nuevo se la salte.

**Panel.** Una sección «Conectores» en la ficha del partner y un bloque «Disponible para» en la ficha del conector. Las dos escriben las mismas filas, y antes de quitar acceso confirman con la lista de clientes afectados.

## Technical Context

**Language/Version**: Python 3.11 (API, worker, MCP); TypeScript con Next.js 16 (panel `apps/admin`).

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic; React 19 en el panel. Sin dependencias nuevas.

**Storage**: PostgreSQL. Dos tablas de plataforma nuevas sin RLS (data-model.md).

**Testing**:
- API: pytest (unit, integration, isolation).
- Worker y MCP: pytest.
- Panel: Vitest con Testing Library.

**Target Platform**: AWS (ECS), igual que hoy.

**Project Type**: Web service con su panel de operador.

**Performance Goals**: una consulta más por turno dentro de `tool_policy`, sobre dos tablas de decenas de filas. Despreciable.

**Constraints**:
- La regla falla cerrado en el turno: si no se puede leer, el turno se queda sin herramientas de conectores.
- Ningún cambio de comportamiento al desplegar: todo habilitado.

**Scale/Scope**: unos 10 partners y unos 30 conectores en el catálogo.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | La regla solo **quita** herramientas (garantía 2). El cliente y su partner salen de la sesión, nunca de un argumento. Test `tests/isolation/test_060_connector_partner_access.py` por el camino real del turno, y barridos AST de altas y cargadores. |
| II | Corte por superficie de confianza | ☑ | Superficie `0`: el panel, la consola y su API, que ya existen. |
| III | Lo leído es dato, nunca instrucción | ☑ | No lee contenido externo. |
| IV | Acción consecuente con confirmación; auditoría nombra a la persona | ☑ | Quitar acceso pide confirmación con los afectados (409 `confirm_required`). Cada cambio se audita con `operator_actor` y el motivo. No borra datos de clientes. |
| V | Estados honestos; la ausencia se diseña | ☑ | En la consola, un conector no disponible no aparece: ni botón apagado ni aviso. En el panel hay estados de carga, vacío, error, parcial (Composio caído) e ideal. |
| VI | Por API, nunca navegando la consola | ☑ | No aplica: no hay agente operando la consola. |
| VII | Test primero; nada de `skip` | ☑ | Cada criterio EARS tiene su test, escrito en rojo antes de implementar (tasks.md, fase de tests). |
| VIII | Licencias | ☑ | Sin dependencias nuevas. |
| IX | KB dueña del porqué | ☑ | `[[decisions/2026-11-13-acceso-a-conectores-por-partner]]`. |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Garantía 2 (lista blanca): la disponibilidad solo resta. Garantía 1 rozada: la regla es dato sin cliente que se lee desde la sesión del cliente. | T010, T011, T012 y T013 en `tests/isolation/`, y T014 (barridos AST) |
| **Licencias** | Ninguna dependencia nueva | — |
| **Medidor** | Nada: no gasta modelo, reloj ni herramientas de pago | — |

**Complejidad que hay que justificar:** ver Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/060-acceso-conectores-por-partner/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/admin-api.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code

```text
apps/api/
├── alembic/versions/0232_connector_partner_access.py      # tablas, GRANT, vocabulario de auditoría
├── src/nexus_api/db/models/connector_access.py            # ConnectorAccessDefault, ConnectorPartnerAccess
├── src/nexus_api/services/connectors/availability.py      # la regla, los afectados, ensure_connector_available
├── src/nexus_api/services/connectors/catalog.py           # audience obligatorio en list_catalog/get_catalog_entry
├── src/nexus_api/services/connectors/service.py           # ensure_connector_available en las altas
├── src/nexus_api/services/activations.py                  # tool_policy bloquea lo no disponible
├── src/nexus_api/services/agent_spec/validator.py         # ToolInfo.withheld; conservar las ya guardadas
├── src/nexus_api/api/console/{tools,agent_integrations,capabilities_client}.py
├── src/nexus_api/api/admin/connector_access.py            # rutas nuevas (contracts/admin-api.md)
├── src/nexus_api/api/admin/{connectors,tool_catalog}.py   # campos access / available_for_partner
└── tests/
    ├── isolation/test_060_connector_partner_access.py
    ├── unit/connectors/test_availability_rule.py
    ├── unit/test_060_sweeps.py                             # barridos AST de altas y cargadores
    └── integration/connectors/test_connector_access_admin.py
apps/mcp/src/nexus_mcp/
├── _connector_access.py                                   # comprobación compartida por los cargadores
└── servers/{amigable_cobro,woocommerce,inventory}/tools.py
apps/admin/src/
├── app/(dashboard)/partners/[id]/connectors/…             # vista por partner (ruta exacta en tasks)
├── app/(dashboard)/connectors/[slug]/…                    # bloque «Disponible para»
├── app/(dashboard)/connectors/connectors-catalog.tsx      # marca de acceso
├── app/(dashboard)/tenants/[id]/connectors/…              # «No disponible para su partner»
└── lib/backend.ts                                         # tipos y llamadas
docs/admin.md, docs/console.md                             # se actualizan en el mismo cambio
```

## Diseño por capas

### La regla (`availability.py`)

- `unavailable_slugs_for_tenant(session, tenant_id) -> frozenset[str]`: una consulta. Lee `tenants.partner_id` y aplica la fórmula de data-model.md, menos canales y sistema.
- `ensure_connector_available(session, tenant_id, slug)`: lanza `ConnectorUnavailable`, que las rutas de la consola traducen a `404 integration_unknown`.
- `effective_for_partner(session, partner_id)` y `access_for_connector(session, slug)`: alimentan las dos vistas del panel.
- `affected_by(session, slug, losing_partner_ids, include_partnerless)`: devuelve clientes con conexión viva por partner, el número de agentes con activación y los partners cuyo `default_connector_slug` es ese slug.

### Turno

- `tool_policy` llama a `unavailable_slugs_for_tenant` antes del bucle. Dentro, la primera comprobación de cada fila es `if slug in unavailable: blocked.add(name); continue`, antes de cualquier otro `continue`.
- Necesita `Connector.slug` en el `select`.

### Procesos programados

- `nexus_mcp/_connector_access.py` expone `connection_is_available(session, tenant_id, slug)`.
- Los tres cargadores lo llaman tras encontrar la conexión viva. Si no está disponible, lanzan la misma excepción que «sin conexión», que los procesos ya saben saltar.

### Altas

`ensure_connector_available` en `initiate_consent`, `bootstrap_api_key` y `bootstrap_browser_credentials`. En `complete_consent_from_webhook`, un conector no disponible deja la conexión `failed` y lo audita.

### Catálogo de la consola

- `audience` obligatorio en `list_catalog` y `get_catalog_entry`.
- `capabilities_client._rows` filtra.
- `validator.load_context` marca `withheld`.

### Panel

Dos vistas y una marca en el catálogo y en la ficha de conectores de un cliente. Los componentes y el patrón de formularios siguen a `partners/[id]/modules` y a los diálogos de `models`. Las rutas exactas están en tasks.md.

## Complexity Tracking

| Añadido | Por qué hace falta | Alternativa más simple descartada |
|---|---|---|
| Valor por defecto por conector (tabla `connector_access_defaults`) | Sin él, un partner nuevo hereda un conector pensado para uno (Quédate). | Solo decisiones por partner: obliga a deshabilitar a mano en cada partner nuevo. |
| Dos barridos AST (altas y cargadores) | Constitución §I: un arreglo donde se vio deja el defecto donde no se miró. | Enumerar los sitios conocidos en el test: no caza el siguiente. |
| `audience` obligatorio en `list_catalog` | `mypy --strict` obliga a cada llamada nueva a decidir. | Un filtro aparte que hay que acordarse de llamar. |
