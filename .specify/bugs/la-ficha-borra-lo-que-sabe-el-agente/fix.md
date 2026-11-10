# Bug Fix: editar la ficha borra lo que sabe el agente

- **Slug**: la-ficha-borra-lo-que-sabe-el-agente
- **Fixed**: 2026-10-29
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`compile_version` recompila desde el AgentSpec de la versión cuando lo tiene,
con `compile_spec(spec, facts)`, que es lo mismo que hace `write_spec` al
escribir el borrador. Las versiones sin AgentSpec siguen con
`compile_prompt(instructions_of(…))`.

## Changes

| File | Change | Notes |
|---|---|---|
| `apps/api/src/nexus_api/services/business/compilation.py` | modified | `compile_version`: rama con AgentSpec. Importación local para no crear un ciclo (`compiler` ya importa `compilation`) |
| `apps/api/tests/integration/business/test_recompile_keeps_agent_layer.py` | added | Tres pruebas: la capa del agente sobrevive, el prompt es el de `write_spec` y una versión sin AgentSpec compila igual que hoy |
