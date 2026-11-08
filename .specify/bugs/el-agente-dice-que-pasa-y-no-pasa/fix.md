# Bug Fix: el agente dice que pasa la conversación y no la pasa

- **Slug**: el-agente-dice-que-pasa-y-no-pasa
- **Fixed**: 2026-11-08
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`_filter_tools_for_intent` añade `escalate.escalate_to_human` (`_EVERY_INTENT_NATIVE`) a la intención
del turno si está en la lista blanca del agente. No cambia nada para quien no la tiene.

## Files

- `apps/worker/src/nexus_worker/runtime/pipeline.py`
- `apps/worker/tests/unit/test_intent_tool_filter.py` (`TestHandOffOnEveryIntent`)
