# Bug Fix: el recordatorio que programa el agente nunca sale

- **Slug**: el-recordatorio-programado-no-sale
- **Fixed**: 2026-10-22
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

El cron de recordatorios lee las claves que escribe la herramienta
(`template_name`, `parameters`) y, por compatibilidad, las antiguas (`template`,
`params`). Además pasa el idioma cuando la fila lo trae, que antes tiraba. La
prueba nueva programa el recordatorio con la herramienta, no a mano.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/worker/src/nexus_worker/streams/reminder_cron.py` | modified | `template_name`→`template`, `parameters`→`params`, `language` si viene; el mensaje de error nombra la clave buena |
| `apps/api/tests/integration/channels/test_reminder_cron.py` | modified test | `test_reminder_scheduled_by_the_tool_is_sent` (productor real) y `test_reminder_legacy_payload_keeps_its_language` |

## Diff Highlights

```python
template_name = payload.get("template_name") or payload.get("template")
...
"parameters": payload.get("parameters") or payload.get("params") or {},
...
language = payload.get("language")
if isinstance(language, str) and language:
    args["language"] = language
```

## Deviations from Assessment

- La «constante compartida de claves» que proponía la evaluación no se añadió:
  la prueba con el productor real ya ata las dos piezas y una constante en
  `nexus_mcp` importada por el worker no añade nada que la prueba no vea.

## Follow-ups

- Reintentos sin tope de un job que falla al despachar: lo resuelve la spec 043,
  que construye los recordatorios de Reservas.
