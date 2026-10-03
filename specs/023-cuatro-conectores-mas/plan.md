# Implementation Plan: tres conectores más

**Branch**: `023-cuatro-conectores-mas` | **Date**: 2026-09-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/023-cuatro-conectores-mas/spec.md`

## Summary

Stripe, Calendly y HubSpot ya aparecen en Conectores porque existen en el
proveedor de consentimientos; esta spec los hace **servir**: cada uno en su
categoría con una frase, con una **lista cerrada** de herramientas (12 / 10 /
11) escrita por Auphere que la sincronización filtra antes de tocar el
catálogo, con nombre de negocio para cada una, las de lectura encendidas al
conectar y las de escritura bloqueadas hasta que un operador las abra. Las
plantillas de citas recomiendan Calendly junto a AgendaPro y la de cobranza
Stripe junto a Amigable Cobro. Sin migración, sin endpoint nuevo, sin
dependencia nueva: cuatro tablas en código, un campo en una respuesta y
tres frases en la consola.

## Technical Context

**Language/Version**: Python 3.14 (API) · TypeScript 5 / Next.js 16 (consola)

**Primary Dependencies**: FastAPI · SQLAlchemy async · el cliente de Composio existente (`services/connectors/composio_client.py`) — **ninguna nueva**

**Storage**: PostgreSQL; ninguna migración. Las filas de `tool_catalog` las crea la sincronización que ya existe, filtrada

**Testing**: pytest (`unit/connectors`, `integration/connectors` con `FakeComposioClient`); vitest en la consola; staging con las tres cuentas reales para cerrar la Historia 1

**Target Platform**: API en AWS, consola en Vercel

**Project Type**: monorepo — servicio web + consola

**Performance Goals**: sincronizar Stripe (426 herramientas del proveedor) deja 12 filas y termina en el mismo tiempo que hoy: el filtro es en memoria, una sola llamada al proveedor como ahora

**Constraints**: lo desconocido nace bloqueado (spec, Requisito 5.3) · lo que el proveedor devuelve es dato (constitución III) · cambiar la lista es un cambio de código con revisión, no de operador (Requisito 2.4) · copy sin siglas ni nombres técnicos

**Scale/Scope**: tres toolkits, 33 herramientas con nombre, 11 plantillas que ganan un bloque opcional

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto, nunca del llamante | ☑ | Ninguna garantía cambia. El catálogo de herramientas es de plataforma (como hoy); la cuenta conectada y la lista blanca del agente siguen por tenant y por RLS. No entra ninguna lectura nueva de datos de tenant. Test de integración `test_sync_allowlist`: sincronizar un conector no toca filas de otro |
| II | Corte por superficie de confianza | ☑ | Superficie `0`. Misma llamada al proveedor que hoy, filtrada |
| III | Lo leído es dato, nunca instrucción | ☑ | La descripción que devuelve el proveedor se guarda en `tool_catalog.description` como hoy; el nombre y la descripción que ve el partner son de Auphere (`capability_names.py`). El slug no se interpreta: se compara con una lista |
| IV | Acción `mutates` con aprobación; auditoría nombra a la persona | ☑ | Sincronizar ya audita `connector.tools.synced`; gana `missing` y `dropped_count`. Abrir una capacidad de escritura sigue siendo acción de operador, fuera de esta spec |
| V | Estados honestos; la ausencia se diseña | ☑ | Un conector sin *auth config* no tiene tarjeta (Requisito 1.3); una herramienta fuera de la lista no existe en pantalla; una de la lista que el proveedor retiró pasa a `deprecated` y deja de verse, y el registro lo dice (D1) |
| VI | Por API `console.*`, nunca navegando la consola | ☑ | El Companion no entra en esta spec |
| VII | Test primero | ☑ | Requisito 3.2 nace como test que recorre la lista (D3); el filtro de sincronización nace con el test de 3 + 2 (quickstart) |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | La KB es dueña del porqué | ☑ | `[[sessions/2026-09-29-spec-021-el-numero-se-puede-mover]]` (continuación 2026-09-30, revisión de Composio); al cerrar, nota propia de sesión |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Ninguna garantía de `architecture/agent-isolation.md` cambia de promesa; no entra ninguna lectura por tenant nueva. Test de integración (no de aislamiento) de que la sincronización filtrada no toca otros conectores | `T-ISO` en `tests/integration/connectors/test_sync_allowlist.py` |
| **Licencias** | Ninguna dependencia nueva | `T-LIC` (comprobación en el plan; sin tarea de código) |
| **Medidor** | Nada nuevo: las herramientas de Composio ya se ejecutan por `execute_tool` y se miden como herramienta de pago cuando lo son | `T-MET` (sin tarea de código) |

## Project Structure

### Documentation (this feature)

```text
specs/023-cuatro-conectores-mas/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/connectors.md
├── evidence/README.md          # auth configs, tamaños de toolkit, slugs reales
└── tasks.md                    # lo crea /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── src/nexus_api/
│   ├── services/connectors/
│   │   ├── toolkits.py                     # NUEVO: TOOLKIT_ALLOWLISTS (stripe · calendly · hubspot)
│   │   ├── service.py                      # sync_tools_for filtra por lista; _derive_annotations la consulta; fuera CALENDLY_* de _TOOL_SLUG_ANNOTATIONS
│   │   └── catalog.py                      # _CATEGORY_BY_TOOLKIT; payment/commerce en _CATEGORY_MAP y _CATEGORY_KEYWORDS
│   ├── services/templating/
│   │   ├── seed_templates.py               # SeedTemplate.connectors_recommended
│   │   └── seeds/*_v1.yaml                 # bloque connectors.recommended (9 plantillas)
│   └── api/console/
│       ├── capability_names.py             # 33 entradas nuevas
│       ├── schemas_agent_tools.py          # ConnectorOut.recommended
│       └── tools.py                        # _connectors rellena recommended
└── tests/
    ├── unit/connectors/test_toolkit_allowlists.py      # NUEVO
    ├── unit/connectors/test_annotation_derivation.py   # + casos de lista
    ├── unit/test_capability_names.py                   # + las 33
    ├── unit/test_connector_category.py                 # NUEVO
    ├── unit/test_seed_templates_connectors.py          # NUEVO
    ├── integration/connectors/test_sync_allowlist.py   # NUEVO
    └── integration/connectors/test_connectors_recommended.py  # NUEVO

apps/console/src/
├── lib/backend/…                           # Connector.recommended
├── components/integrations/connector-card.tsx   # insignia «Recomendado para tu sector»
├── components/integrations/__tests__/…     # tarjeta: frase y insignia
└── i18n/lanes/capabilities.ts              # connectors.desc.{stripe,calendly,hubspot} · connectors.badge.recommended
```

**Structure Decision**: la lista cerrada va en un módulo propio
(`toolkits.py`) y no dentro de `service.py`, porque es un dato de producto
que se leerá y revisará más que el código que lo aplica, y porque el test de
«todo slug tiene nombre» lo importa junto a `capability_names` sin arrastrar
la sesión de base de datos.

## Fase 1 — diseño

| Artefacto | Qué fija |
|---|---|
| [`research.md`](research.md) | D0–D6: las tres listas con sus nombres, la categoría por toolkit, el campo `recommended`, las frases |
| [`data-model.md`](data-model.md) | La forma de la lista, las filas que produce, el bloque de plantilla, el campo de salida, la auditoría |
| [`contracts/connectors.md`](contracts/connectors.md) | Los dos endpoints que cambian de contenido y el contrato de la sincronización |
| [`quickstart.md`](quickstart.md) | La suite local con el proveedor simulado y los seis pasos en staging con cuentas reales |

### El orden de entrega

1. **La lista y el filtro** (API): `toolkits.py`, filtro en `sync_tools_for`,
   anotaciones de la lista, registros y auditoría, test de 3 + 2. Con esto
   Calendly, que ya existía con 53, pasa a 10 en la primera sincronización.
2. **Nombre, categoría y frase**: `capability_names.py` (con el test que no
   deja hueco), `_CATEGORY_BY_TOOLKIT`, tres claves en la consola. Historia 1
   completa en local; en staging, confirmar los slugs en el panel y conectar
   las tres cuentas (quickstart, pasos 1–5).
3. **Recomendación**: bloque en las plantillas, `SeedTemplate`,
   `ConnectorOut.recommended`, insignia en la tarjeta. Historia 2.

## Complexity Tracking

| Añadido | Por qué hace falta | Alternativa más simple, y por qué no |
|---|---|---|
| Módulo `toolkits.py` con listas por toolkit | Requisito 2.3: solo una lista cerrada llega al agente; 426 filas de Stripe no pueden entrar en `tool_catalog` ni en la lista blanca | Esconder en la consola lo que no interesa: seguiría sincronizado y dentro de la lista blanca del agente |
| `_CATEGORY_BY_TOOLKIT` además de las palabras clave | Requisito 1.1 no puede depender de la etiqueta que publique el proveedor | Solo palabras clave: bastaría hoy, pero un cambio de etiqueta ajeno movería Stripe a «otros» sin que nadie lo viera |
| Bloque `connectors.recommended` en las plantillas y campo `recommended` en `ConnectorOut` | La spec suponía que «recomendado» existía en Conectores; solo existe en Capacidades y no sirve para conectores (D4) | Meter slugs de Composio en `tools_required`: intentaría encender herramientas que no existen hasta conectar |
