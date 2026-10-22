# Bug Verification: Google Calendar y Calendly se conectan pero el agente no recibe herramientas, y reintentar da 502

- **Slug**: conector-de-calendario-sin-herramientas
- **Tested**: 2026-10-22 (local, base propia `nexus_test_hotfix`, Redis db 13)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified en local; sin desplegar

## Red before the fix

| Prueba | Antes |
|---|---|
| `test_composio_live_list_tools.py` (3) | 3 en rojo: la lista sale con `slug=""` |
| `test_a_second_consent_after_the_owner_already_authorised_settles_it` | `502 == 409`, `{"detail":"fake: Multiple connected accounts found …"}` — el mismo 502 de producción |
| `test_tenants_still_being_set_up_are_reconciled_too` | rojo: el cron solo pide `active` |

## Green after the fix

| Suite | Resultado |
|---|---|
| `test_composio_live_list_tools.py` | 3 passed |
| `test_endpoint_console_agent_tools.py` | 12 passed |
| `test_connector_reconcile_cron.py` | 2 passed |
| `./scripts/verify.sh lint` | verde |
| `./scripts/verify.sh py` | ver `imagen-de-prod-fuera-del-lock/test.md` |

`get_raw_composio_tools` tiene la misma firma en `composio` 0.13.0 (lock) y en
0.28.0 (la que llevaba la imagen; leída del wheel, sin instalar).

## Not covered

- Una llamada real a Composio: las pruebas usan el falso, que ahora imita el
  rechazo del SDK a una segunda cuenta `ACTIVE`.
- El webhook de Composio: es configuración de su panel.
