# Bug Fix: el agente dice que pasa la conversación y no la pasa

- **Slug**: el-agente-dice-que-pasa-y-no-pasa
- **Fixed**: 2026-11-08
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`_filter_tools_for_intent` añade `escalate.escalate_to_human` (`_EVERY_INTENT_NATIVE`) a la intención
del turno si está en la lista blanca del agente. No cambia nada para quien no la tiene.

Segunda parte, tras repetirlo en staging (20:47 UTC): con la herramienta ya en el turno, el modelo
la usó en el Playground y no en un WhatsApp real («para mi hermana…»: `tool_calls: 0`). Luis eligió
reforzar el texto y no un freno de plataforma: cuando el turno ofrece la herramienta, una nota del
sistema (`_HAND_OFF_NOTE`) dice que pasar la conversación es llamarla en ese turno y que nunca se
dice sin haberla llamado. Vale para todos los agentes sin volver a publicarlos.

## Files

- `apps/worker/src/nexus_worker/runtime/pipeline.py`
- `apps/worker/tests/unit/test_intent_tool_filter.py` (`TestHandOffOnEveryIntent`)
- `apps/worker/tests/unit/test_hand_off_note.py`
