# Bug Verification: un cliente final puede hacerse programar recordatorios de pago sin tope

- **Slug**: recordatorios-sin-tope
- **Tested**: 2026-10-22 (local, base propia `nexus_test_recordatorios`, Redis db 11)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

Antes del arreglo la herramienta aceptaba cualquier plantilla, a cualquier fecha
y sin límite por cliente. Ahora solo programa las plantillas que permite el
agente del número, hasta 3 por cliente en 24 h y 30 días por delante (o lo que
diga su política, con techos de 10 y 365), y dos llamadas simultáneas no se
quedan las dos con el último hueco.

## Red before the fix

`tests/integration/mcp/test_schedule_reminder_limits.py` sobre el código sin
cambiar: **12 en rojo, 6 en verde**. Los 12 rojos fallan por la razón esperada
(`DID NOT RAISE ToolError`; la de concurrencia programó 4 de 4 con tope 1). Los 6
verdes comprueban lo que debe seguir permitido (plantilla de la lista, horizonte
ampliado por la política, `run_at` vencido, otro cliente, cancelados, más de
24 h): pasaban antes y deben seguir pasando después.

## Green after the fix

| Suite | Resultado |
|-------|-----------|
| `test_schedule_reminder_limits.py` | 18 passed |
| `tests/integration/mcp` + `test_mcp_dry_run_per_server.py` | 79 passed |
| `./scripts/verify.sh lint` | verde (ruff y formato de los cuatro paquetes; mypy --strict api, worker, channels, mcp) |
| `./scripts/verify.sh py` | verde: API 4 971 passed / 415 skipped / 4 xfailed; worker 442; channels 61; MCP 123 |

Las dos pruebas del happy path que usaban la herramienta
(`test_notification_send_template_and_text_and_schedule_and_cancel`,
`test_flow1_booking_with_preferred_barber_smoke`) cayeron con el arreglo por no
tener política, como se esperaba, y vuelven a verde sembrándola.

## Not covered

- El extremo a extremo con el cron: en `main` el cron aún lee `template` y no
  `template_name` (su arreglo está en la rama de consolas-web). Al fusionar,
  ver el seguimiento de `fix.md` sobre `test_reminder_scheduled_by_the_tool_is_sent`.
- Ningún tenant real tiene todavía `policies.scheduled_reminders`.
