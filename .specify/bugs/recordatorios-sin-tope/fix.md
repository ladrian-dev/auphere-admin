# Bug Fix: un cliente final puede hacerse programar recordatorios de pago sin tope

- **Slug**: recordatorios-sin-tope
- **Fixed**: 2026-10-22
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`notification.schedule_reminder` solo programa lo que permite el agente que
contesta en el número de la conversación, en `policies.scheduled_reminders`:
sus plantillas (sin lista, ninguna), como mucho 3 por cliente en 24 h y 30 días
por delante, con techos de 10 y 365 aunque la política diga más. El recuento va
bajo un bloqueo por cliente, así que dos llamadas a la vez no se cuelan las dos.
Cada negativa deja un `notification.schedule_reminder.refused` en el log con el
motivo.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/mcp/src/nexus_mcp/servers/notification/tools.py` | modified | `ReminderPolicy`, `_reminder_policy` (agente del número, como `payments.request_review`), `_assert_reminder_quota` con `pg_advisory_xact_lock`; `run_at` sin desfase se lee como UTC; descripción con los límites |
| `apps/api/tests/integration/mcp/test_schedule_reminder_limits.py` | new test | 18 pruebas: plantillas, horizonte, cupo diario, techos, agente del número, concurrencia |
| `apps/api/tests/integration/mcp/conftest.py` | modified test | `seed_reminder_policy` |
| `apps/api/tests/integration/mcp/test_servers_happy_path.py` | modified test | sus dos usos de la herramienta siembran la política |

## Diff Highlights

```python
policy = await _reminder_policy(session, conv)
if not policy.templates:
    raise _refuse_reminder("no_templates", ...)
if payload.template_name not in policy.templates:
    raise _refuse_reminder("template", ...)
if run_at - datetime.now(UTC) > timedelta(days=policy.days_ahead):
    raise _refuse_reminder("days_ahead", ...)
await _assert_reminder_quota(session, policy, tenant_id=..., customer_id=conv.customer_id)
```

```python
await session.execute(
    text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
    {"key": f"schedule_reminder:{tenant_id}:{customer_id}"},
)
# count: kind=reminder, status != cancelled, created_at in the last 24 h,
# payload.conversation_id among the customer's conversations
```

## Deviations from Assessment

Ninguna.

## Follow-ups

- **Al fusionar con la rama de consolas-web** (`agitated-robinson-dd06ff`, commit
  `fix(worker): send scheduled reminders that carry template_name`): su
  `test_reminder_scheduled_by_the_tool_is_sent` programa con la herramienta sin
  política y fallará con «no template enabled for reminders». Basta con sembrar
  antes un `AgentConfig` activo con
  `policies={"scheduled_reminders": {"templates": ["reminder_24h"]}}` (el
  `seed_reminder_policy` de `tests/integration/mcp/conftest.py` hace eso).
- Configurar `policies.scheduled_reminders.templates` de los clientes que deban
  enviar recordatorios del agente. No hay pantalla: va por la API de versiones de
  agente (el editor del Admin conserva `policies` tal cual al guardar).
- `notification.send_template` tampoco tiene lista ni tope y está entre las
  herramientas requeridas de las semillas (ver la evaluación).
