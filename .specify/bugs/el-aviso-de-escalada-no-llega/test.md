# Bug Verification: el aviso de escalado por WhatsApp no llega

- **Slug**: el-aviso-de-escalada-no-llega
- **Tested**: 2026-11-08 (local, base propia `nexus_test_escalation`, Redis db 6)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified (código); pendiente de la configuración en staging

## Summary

El aviso por WhatsApp sale en el idioma en que la plantilla está aprobada en el
WABA del número que lo manda; el número del cliente solo se usa si su WABA la
tiene; si no, el de Auphere. Sin ninguno de los dos, el aviso no sale, no se da
por enviado, deja `escalation_whatsapp_unavailable` y un único evento por
cliente, y la página del canal lo enseña. Nada sale a Meta en las pruebas.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Línea base (antes de tocar nada) | `pytest` de `test_operator_alerter*.py`, `test_escalation_recipients.py`, `test_channel_config.py` | pass | 28 passed |
| Reproducción (antes del arreglo) | las mismas + `test_operator_alert_sender.py` nuevas | fail | vía de siempre 5 de 6 en rojo (`'es_CL' == 'es'`, `'es_CL' == 'es_ES'`, manda del cliente sin plantilla, sin ajuste de idioma, sin motivo claro); canal 4 en rojo (idioma, firma del envío de Auphere, sin motivo); página 1 en rojo (`KeyError: 'escalation_template_missing'`) |
| Reproducción (después) | las mismas | pass | 38 passed (28 + 10 nuevas) |
| Todo lo que toca avisos, `notify_from` y la página del canal | 25 archivos de `apps/api/tests` (alerter, escalado, página, menú y método del canal, enlace del dueño, despachador, corte de presupuesto, credenciales, migración 0192, push, bolsa, números de Auphere, unitarias de audiencia y correo) | pass | 225 passed |
| Worker (proceso aparte) | `test_agent_tests_failing.py`, `test_platform_alarms_contract.py`, `test_bootstrap_split.py`, `test_allocation_debit_wiring.py` | pass | 35 passed |
| Aislamiento de la consola | `pytest tests/isolation/test_console_scope.py` | pass | 1621 passed. No se tocan endpoints, sí lo que devuelve la página del canal |
| Consola | `vitest` de `channel-model.test.ts` y `channel-page.test.tsx` | pass | 43 passed; sin el arreglo, 2 en rojo |
| Textos de la consola | `vitest src/i18n` (incluye «sin punto y coma») | pass | 67 passed |
| Consola, tipos y lint | `tsc --noEmit`, `eslint --max-warnings 0` de lo tocado | pass | |
| Lint | `./scripts/verify.sh lint` | pass | ruff y format de los cuatro paquetes y renderer; `mypy --strict` de api, worker, channels, mcp y renderer |

## Residual Risks

- **Configuración**: hasta que un operador registre el número de avisos de
  Auphere en staging (fix.md §1), los clientes sin la plantilla siguen sin aviso
  por WhatsApp; ahora con motivo y con la comprobación en la página.
- **El idioma de Auphere va por configuración**: si la WABA de Auphere tiene
  `alert_escalation_v1` en otro idioma que `NEXUS_AUPHERE_ALERT_TEMPLATE_LANGUAGE`,
  Meta seguirá devolviendo 132001 desde Auphere. No se puede comprobar desde el
  código (no hay espejo de esa WABA).
- **No probado contra Meta real** ni en staging: el envío del cliente usa el
  adaptador falso y el de Auphere se sustituye o no existe.
- Los avisos que ya fallaron no se reenvían: eran escalados ya atendidos o
  vencidos.

## Recommendation

Fusionar con el resto de `develop`, hacer los pasos de configuración de fix.md
en staging y confirmar en `/nexus/staging/scheduler` un
`operator_alerter.channel_recipients_sent` con `notify_from` y `language` tras
un escalado de prueba. Cerrar el bug entonces.
