# Bug Test: el constructor de agentes no termina nunca

- **Slug**: el-constructor-corta-a-los-30-segundos
- **Date**: 2026-11-04

`apps/worker/tests/unit/test_builder_call_budget.py` fija el plazo, los reintentos a 0 y
que el trabajo deje sitio a dos llamadas. Un turno de chat sigue con sus 30 s.

**Sin verificar:** no se puede llamar al modelo real desde local. Se comprueba en staging
al desplegar: `builder.job kind=agent_draft status=done` y, si falla, `cause` en
`jobs.agent_draft.unavailable`.
