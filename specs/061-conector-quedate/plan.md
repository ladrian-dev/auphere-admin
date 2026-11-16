# Plan de implementación: Conector de Quédate (enmienda del 2026-11-16)

**Rama**: `061-conector-quedate` · **Spec**: [spec.md](spec.md) · **Investigación**: [research.md](research.md)

## Summary

`quedate` es un conector por clave. Cada cliente pega **su** clave de la API del agente de Quédate y, si quiere probar, el entorno dev. Tiene 27 herramientas en cuatro grupos:
- **catálogo y públicas** (6);
- **fotos de la conversación** (1);
- **de la persona que escribe** (9): su anfitrión sale de un vínculo resuelto en el servidor;
- **de equipo** (11): cualquier anfitrión de la clave.

Ninguna publica directamente: solo mandan a revisión de Quédate u ocultan. El vínculo persona → anfitrión vive en `customer_connector_accounts`, ya sin credencial.

## Technical Context

- **Language/Version**: Python 3.11 (API, MCP, worker) y TypeScript con Next.js 16 (panel y consola).
- **Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, httpx y Pydantic 2. Sin dependencias nuevas.
- **Storage**: PostgreSQL:
  - una tabla de tenant con RLS (`customer_connector_accounts`);
  - filas en `connectors`, `tool_catalog`, `connector_access_defaults` y el vocabulario de auditoría.
- **Testing**:
  - pytest con transporte falso y respuestas reales de dev, sin claves;
  - isolation con la base;
  - Vitest en el panel;
  - una pasada real contra dev con la clave de Luis, fuera de la suite.
- **Constraints**:
  - la salida de una herramienta, por debajo de 8.000 caracteres;
  - el inventario de `test_51` sube en 3 entradas razonadas;
  - Quédate no borra: nada que cree se reintenta solo.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | Garantía 8: el anfitrión de la persona sale del vínculo, nunca de un argumento. Se comprueba la pertenencia del anuncio antes de escribir. Garantía 1: RLS, FK compuesta y FK a `tenants`. Test `tests/isolation/test_061_customer_connector_accounts.py`. |
| II | Superficie | ☑ | `0`. La credencial es la del cliente (`tenant_credentials`, como cualquier conector por clave). El ADR de credencial por persona se enmienda: ahora es un vínculo sin secreto. |
| III | Lo leído es dato | ☑ | Lo que devuelve Quédate entra como resultado de herramienta y se recorta a campos conocidos. |
| IV | Acción consecuente | ☑ | Conectar no activa nada. El partner da el permiso por agente; con «Preguntar antes de escribir», el dueño aprueba cada escritura. El agente nunca publica: manda a revisión de Quédate. Las fotos y los documentos los elige la persona. |
| V | Estados honestos | ☑ | «Quédate no responde» y «puede que se haya creado» se dicen tal cual. El panel muestra los vínculos en sus estados. |
| VI | Por API | ☑ | La API del agente de Quédate. |
| VII | Test primero | ☑ | Tests en rojo por requisito y mutaciones de las salvaguardas. |
| VIII | Licencias | ☑ | Sin dependencias nuevas. |
| IX | KB | ☑ | Nota de alcance con su cambio de premisa, investigación y ADR enmendado. |

## Project Structure

```text
apps/mcp/src/nexus_mcp/
├── http/base_client.py            # +files (multipart) en request(), retrocompatible
└── servers/quedate/
    ├── errors.py
    ├── client.py                  # QuedateClient(base por entorno): agente y general
    ├── schemas.py
    ├── accounts.py                # conexión (clave y entorno), vínculo, candado y auditoría
    ├── photos.py                  # imágenes de la conversación del turno
    └── tools.py                   # 27 herramientas + QUEDATE_TOOLS
apps/mcp/tests/                    # contrato con respuestas reales de dev, persona, equipo y públicas
apps/api/alembic/versions/0233_quedate_connector.py (+ data/0233_quedate_tools.json)
apps/api/src/nexus_api/db/models/customer_connector_account.py   # sin credencial
apps/api/src/nexus_api/services/connectors/{key_check.py, seeds/quedate.yaml}
apps/api/src/nexus_api/api/console/capability_names.py
apps/api/tests/isolation/test_061_customer_connector_accounts.py (+ test_51 y test_44)
apps/admin/…/tenants/[id]/connectors/[slug]/customer-accounts.tsx
apps/console/src/i18n/lanes/                                       # connectors.field.quedate.*
```

## Diseño por capas

- **Cliente**:
  - `QuedateClient(environment, token?)` lleva dos bases fijas por entorno: la del agente y la general.
  - Errores: 401 → `AuthError`, 403 → `Forbidden`, 404, 409, 422 (con el campo), 429 y 5xx o transporte → `Unavailable`.
  - Las escrituras no se reintentan.
- **Conexión**: `require_connection` devuelve la clave y el entorno: la clave de `tenant_credentials` (`{"api_key"}`) y el entorno de `endpoint_meta.environment`. Llama a `connection_is_available`.
- **Vínculo**: `load`, `save` (sustituye), `mark_review`, `save_state`, `audit` y `lock`. Ninguna función recibe la persona de un argumento.
- **Fotos**: la última conversación del cliente del turno, sus mensajes entrantes `image` de 24 h, como mucho 20, y los bytes del almacén de medios.
- **Comprobación de la clave**: `key_check` hace `GET /agent/hosts?per_page=1` en el entorno de la conexión.
