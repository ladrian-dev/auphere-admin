# Bug Fix: el chat de prueba y las pruebas del agente esconden que el modelo no respondió

- **Slug**: el-probador-tapa-los-fallos-del-modelo
- **Fixed**: 2026-11-03
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`run_turn` ya no pierde `turn_failure`: el chat lo enseña y una pasada sin modelo queda
sin decidir, con su propio estado («No se pudo probar») y sin contar contra el agente. Si
no se pudo probar nada, el trabajo falla con `model_unavailable`. Los fallos fuera de
canales tienen su alerta, `simulated_model_failure_burst`, porque `turn_error_burst`
le manda un WhatsApp al dueño del negocio.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/worker/src/nexus_worker/simulation/failures.py` | added | Qué cuenta como fallo del modelo y su rastro: registro, métrica y contador |
| `apps/worker/src/nexus_worker/simulation/runner.py` | modified | `TurnOutcome.failure` |
| `apps/worker/src/nexus_worker/simulation/customer.py` | modified | `stop = model_failed` si falla el modelo del agente o el del cliente simulado |
| `apps/worker/src/nexus_worker/jobs/handlers/agent_tests.py` | modified | `_decide`, también si falla el juez cuyo veredicto hacía falta; `model_unavailable` |
| `apps/worker/src/nexus_worker/streams/platform_watcher.py` | modified | La alerta nueva, sin `tenant_id` para no escribir la fila del WhatsApp |
| `apps/api/alembic/versions/0218_test_stop_model_failed.py` | added | El `CHECK` de `stop` |
| `apps/api/src/nexus_api/db/models/agent_spec.py` | modified | `TEST_STOPS` |
| `apps/api/src/nexus_api/services/testing/runs.py` | modified | Estado `model_failed`, `why_untested`; lo no probado queda desactualizado |
| `apps/api/src/nexus_api/services/publishing.py` | modified | `critical_test_untested` y el aviso `test_untested` |
| `apps/api/src/nexus_api/api/console/agent_playground.py` | modified | `TurnOut.failure {reason}`, sin el error del proveedor |
| `apps/api/src/nexus_api/api/console/agent_tests.py` | modified | `TestOut.why_untested` |
| `infra/terraform/30-observability/alarms.tf` | modified | La alarma del tipo nuevo. **Sin aplicar** |
| `apps/console/src/components/builder/agent-playground.tsx` | modified | Aviso bajo la burbuja, sin «¿Por qué dijo esto?». Conserva lo escrito. La conversación se alcanza con el teclado (`tabIndex`) |
| `apps/console/src/components/builder/test-list.tsx`, `tests-box.tsx` | modified | Estado propio, sin «Por qué falló» ni «Arreglar», y aviso con cuántas |
| `apps/console/src/components/builder/publish-bar.tsx` | modified | Dice `model_unavailable`. Un fallo cierra la hoja del diff y lleva el foco al aviso |
| `apps/console/src/components/builder/quality-model.ts`, `agent-proto-model.ts` | modified | Los motivos de fallo, en un solo sitio; lo no probado cuenta como pendiente |
| `apps/console/src/lib/backend/agent-quality-types.ts`, `i18n/lanes/{builder-quality,amendment}.ts` | modified | Tipos y textos |
| `docs/agentes.md`, `docs/correos.md`, `specs/047-la-fabrica-de-agentes/contracts/console-api.md` | modified | Lo que describen |

## Tests Added or Updated

- `apps/api/tests/integration/builder/test_model_failures_are_not_agent_failures.py`: el chat, la suite, el cliente simulado, el juez, una pasada a medias, «Guardar» y `test_the_case_of_staging_a_partner_without_a_key_in_the_proxy`, con el proveedor de verdad, el proxy obligatorio y un partner sin clave.
- `apps/api/tests/unit/test_test_status_without_a_model.py`: la tabla de estados.
- `apps/worker/tests/unit/test_simulation_failures.py`: qué es un fallo del modelo, y que lo que decide el router no lo es.
- `apps/worker/tests/unit/test_platform_watcher.py`: la alerta propia, sin WhatsApp.
- `apps/console/src/components/builder/__tests__/{agent-playground,test-list,publish-bar,tests-box}.test.tsx` y `agent-proto-model.test.ts`.
- `apps/console/e2e/agent-model-failures.e2e.ts`, con la API simulada de `agent-quality-mock.mjs`: el chat, las pruebas y «Guardar» desde la hoja, en Chromium.

## Local Verification

En `./test.md`.

## Deviations from Assessment

- El enunciado proponía contar estos fallos en `turn_error_burst` o dejar escrito por qué no. Se escribió por qué no (`simulation/failures.py`, `docs/correos.md`) y además tienen su alerta.
- `publish-bar` no estaba en la lista de archivos: si no, «Guardar» sin modelo decía «No se pudo guardar».

## Hallazgos de la auditoría de UI

Medidos en Chromium sobre la consola de verdad, con la API simulada y los datos de fallo.

| Gravedad | Dónde | Qué pasaba | Arreglo |
|---|---|---|---|
| 🔴 | `publish-bar.tsx` | Con la hoja del diff abierta, que es el camino normal de un agente con canales, cualquier fallo quedaba detrás del modal: ni se veía ni lo leía un lector de pantalla. También el genérico, de antes de este bug | La hoja se cierra y conserva la nota |
| 🔴 | `agent-playground.tsx` | `scrollable-region-focusable` (serious): a 360 px, un turno fallido ya desborda la conversación, y sin nada enfocable dentro el teclado no llega a lo de abajo | `tabIndex={0}`, con anillo de 4,95:1 en claro y 7,78:1 en oscuro |
| 🔴 | `test-list.tsx` | Un nombre de prueba o un primer mensaje largo y sin espacios desbordaba la fila a 360 px. También de antes | `wrap-anywhere`, que sí reduce el ancho mínimo |
| 🟡 | `publish-bar.tsx` | Tras el fallo, el foco caía en `<body>`, porque el botón que abrió la hoja ya no está | El foco va al aviso |
| 🟡 | `agent-playground.tsx` | Un turno fallido vaciaba la caja: reintentar obligaba a escribirlo otra vez | Conserva lo escrito |
| 🟡 | `agent-playground.tsx` | `role="alert"` dentro de una lista que ya es región viva lo anunciaría dos veces. Leído en el código, sin lector de pantalla | Una nota con los tokens de aviso, sin `role` |
| 🟡 | Chat, lista y tarjeta | A quien solo lee se le pedía repetir lo que no puede | El «vuelve a…» solo a quien puede |

## Follow-ups

- **Decisión para Luis**: `turn_error_burst` tampoco ve los fallos del modelo **en canales**. Solo cuenta los turnos que lanzan una excepción, y el handler no lanza: responde con el texto de emergencia y pasa a una persona. Contarlos es una línea en `execute_due_turn`, pero manda WhatsApp a los dueños durante una caída del modelo, y eso no se cambia sin preguntar.
- La alarma nueva está sin aplicar, como las demás de la spec 051: `terraform apply` con `-target`. Hasta entonces el `platform_alert` se registra y nadie avisa.
- Un turno que agota sus 120 s sigue contando como fallo del agente.
- Una pasada con el modelo caído recorre todas sus pruebas. Con un fallo rápido, como el de staging, son 19 s; con un proveedor que tarda, puede agotar el plazo del trabajo. Cortar antes queda por decidir.
