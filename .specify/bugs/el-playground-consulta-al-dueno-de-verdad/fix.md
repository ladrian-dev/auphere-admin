# Bug Fix: el playground y las pruebas consultan al dueño de verdad

- **Slug**: el-playground-consulta-al-dueno-de-verdad
- **Fixed**: 2026-10-29
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

- **La puerta de aprobación** (`pipeline.py`): con un registro en `dry_run` (el
  playground de la 047, sus pruebas y el playground de antes) el grafo no llama a
  `tool_approvals.gate`. Le dice al registro que habría preguntado
  (`note_simulated_approval`) y sigue como si el dueño hubiera dicho que sí; la
  ejecución es la del dry run, que nunca escribe. Fuera del dry run, nada cambia.
- **El registro simulado** (`simulation/registry.py`): una herramienta de un
  conector —un proxy de Composio, o cualquiera con `connector_id` en el catálogo
  (`load_connector_tools`, que el runner lee en la misma sesión que la versión)—
  no se ejecuta nunca. La de lectura devuelve `{"simulated": true, "data": {}}` y
  «Consultar … (simulado, sin datos reales)»; la de escritura, «Usar …». La
  aprobación queda «Preguntar al dueño antes de …». Lo interno que solo lee datos
  del negocio (la ficha, los servicios) sigue corriendo.

## Lo que apareció al escribir la prueba (arreglado aquí)

1. **El turno simulado no llevaba el agente** (`runner.run_turn`, sin
   `state["agent_id"]`). Con eso, la política de conectores se calculaba sin
   agente: para un partner con la consola nueva **ninguna** herramienta de
   conector llegaba al playground ni a las pruebas, aunque el agente la tuviera
   activada, y el conocimiento y la memoria propios del agente tampoco. El runner
   ahora pone el agente de la versión, como el despachador en el canal. El
   cargador ya estaba fijado a la versión bajo las dos claves (`prime`), así que
   sigue probando el borrador y no la activa.
2. **La vista por turno de Composio perdía el registro simulado**
   (`_view_with_composio` creaba un `MCPRegistry` nuevo): con un conector de
   Composio, el playground dejaba de usar la agenda simulada y estas reglas.
   Ahora la vista es una copia del registro con sus propias tablas
   (`MCPRegistry.view()`), que conserva la clase, el `dry_run`, la auditoría y el
   mundo simulado.

## Decisión

Las lecturas de conectores no se ejecutan ni siquiera «con cuidado»: un sistema
del negocio devuelve datos de sus clientes finales, y el partner no debe verlos
(C8). La prueba que necesite un dato de un conector lo comprueba por la acción
(«Consultar …»), no por su contenido.

## Lo que queda

El playground de antes (`/console/clients/{ref}/playground`, sobre `qa.py`, con
un `MCPRegistry(dry_run=True)` y no el simulado) ya no pregunta al dueño (la rama
del grafo es la misma), pero sus lecturas de conectores sin `side_effects` (las de
WooCommerce, por ejemplo) siguen ejecutándose de verdad, como antes de la 047. La
consola nueva usa el playground de la 047; si el de antes sigue abierto a
partners, conviene darle las mismas reglas o retirarlo.

## Changes

| File | Change | Notes |
|---|---|---|
| `apps/worker/src/nexus_worker/runtime/pipeline.py` | modified | en `dry_run`, `note_simulated_approval` en lugar de `_approval_envelope`; la vista de Composio con `registry.view()` |
| `apps/mcp/src/nexus_mcp/registry.py` | modified | `MCPRegistry.view()` y el gancho `note_simulated_approval` (sin efecto en el registro de siempre) |
| `apps/worker/src/nexus_worker/simulation/registry.py` | modified | reglas de conectores, la aprobación anotada, `load_connector_tools` |
| `apps/worker/src/nexus_worker/simulation/runner.py` | modified | el agente en el estado del turno; las herramientas de conectores del catálogo al registro |
| `apps/worker/tests/unit/test_simulated_registry_connectors.py` | added | el registro simulado |
| `apps/api/tests/integration/connectors/test_playground_never_reaches_the_business.py` | added | el playground de punta a punta, y el canal sin cambios |
| `docs/agentes.md` | modified | el playground no sale del mundo simulado |
