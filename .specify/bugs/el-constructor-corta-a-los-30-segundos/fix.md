# Bug Fix: el constructor de agentes no termina nunca

- **Slug**: el-constructor-corta-a-los-30-segundos
- **Fixed**: 2026-11-04
- **Assessment**: ./assessment.md
- **Status**: applied, sin desplegar

## Summary

Una llamada del constructor espera 120 s y no se repite. El trabajo pasa de 180 a 270 s,
porque puede hacer dos llamadas (la guía generada y el borrador). `client_builder` usa
la misma función y hereda el plazo. El log dice el tipo de la causa.

## Changes

| File | Change |
|------|--------|
| `apps/worker/src/nexus_worker/runtime/llm.py` | Campo `max_retries`; sin él, lo de siempre |
| `apps/worker/src/nexus_worker/jobs/handlers/agent_draft.py` | `BUILD_CALL_TIMEOUT_S`, `TIMEOUT_S`, `cause` en el log |
